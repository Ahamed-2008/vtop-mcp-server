"""Command-line interface: serve (MCP stdio), login (manual CAPTCHA), logout, status.

The login flow is the ONLY place credentials are handled. The user solves the
VTOP CAPTCHA by eye; password entry uses getpass (never echoed, never logged,
never persisted). Resulting sessions persist cookies+CSRF+authorizedID to a
0600 file documented in the README.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import getpass
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from .config import Settings
from .errors import (
    AuthenticationRequiredError,
    CaptchaRequiredError,
    InvalidConfigurationError,
    LoginFailedError,
    VTopError,
)
from .logging_setup import configure_logging, get_logger
from .metrics import Metrics
from .redaction import Redactor
from .server.mcp_server import run_stdio_session
from .vtop.auth import AuthManager
from .vtop.client import LoginChallenge, VTOPClient

console = Console()
log = get_logger("cli")


def _settings() -> Settings:
    try:
        return Settings.from_env()
    except InvalidConfigurationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise SystemExit(2) from exc


def _build_stack(settings: Settings) -> tuple[VTOPClient, AuthManager, Metrics, Redactor]:
    configure_logging(settings.log_level)
    redactor = Redactor()
    metrics = Metrics()
    client = VTOPClient(settings, metrics, redactor)
    auth = AuthManager(client, settings, metrics, redactor)
    return client, auth, metrics, redactor


# ------------------------------------------------------------------ serve
async def _serve(args: argparse.Namespace) -> int:
    settings = _settings()
    client, auth, metrics, _redactor = _build_stack(settings)
    from .services import AcademicService

    service = AcademicService(auth, settings, metrics, _redactor)
    try:
        await auth.bootstrap()
        await run_stdio_session(service, auth, metrics)
    finally:
        await client.close()
    return 0


# ------------------------------------------------------------------ login
def _render_captcha(challenge, settings: Settings) -> Optional[Path]:
    """Write the built-in CAPTCHA to a 0600 temp image and try to display it."""
    if challenge.captcha_image is None:
        return None
    try:
        image_bytes = base64.b64decode(challenge.captcha_image)
    except binascii.Error:
        raise CaptchaRequiredError("VTOP returned an unreadable CAPTCHA image; please retry.")
    if len(image_bytes) < 32:
        raise CaptchaRequiredError("VTOP returned an empty CAPTCHA image; please retry.")

    suffix = ".jpeg" if "jpeg" in challenge.captcha_mime or "jpg" in challenge.captcha_mime else ".png"
    fd, path = tempfile.mkstemp(prefix="vtop_captcha_", suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(image_bytes)
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover
        return None

    opener = shutil.which("xdg-open") or shutil.which("open")
    if args_auto_open() and opener:
        subprocess_run([opener, path])
    return Path(path)


_args_auto_open: bool = True


def args_auto_open() -> bool:
    return _args_auto_open


def subprocess_run(cmd: list[str]) -> None:
    import subprocess

    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:  # pragma: no cover
        pass


async def _login(args: argparse.Namespace) -> int:
    settings = _settings()
    client, auth, _metrics, redactor = _build_stack(settings)
    if not settings.enable_login:
        console.print("[red]Login disabled:[/red] set VTOP_ENABLE_LOGIN=true to allow authentication.")
        return 2

    global _args_auto_open
    _args_auto_open = not args.no_open

    username = args.username
    if not username:
        username = os.environ.get("VTOP_USERNAME", "").strip()
    if not username:
        username = input("VTOP username: ").strip()
    if not username:
        console.print("[red]Username is required.[/red]")
        return 2

    password = args.password or os.environ.get("VTOP_PASSWORD")
    if not password:
        password = getpass.getpass("VTOP password (not echoed): ")

    try:
        challenge = await _fetch_login_challenge(client)
    except VTopError as exc:
        console.print(f"[red]Could not reach the VTOP login page:[/red] {exc.message if hasattr(exc, 'message') else exc}")
        return 3

    captcha = _prompt_captcha(challenge, settings)

    try:
        session = await auth.login(username, password, captcha, challenge=challenge)
    except LoginFailedError as exc:
        console.print(f"[red]Login failed:[/red] {exc}")
        console.print("Tip: VTOP rejects the CAPTCHA fairly often — try again with a fresh code.")
        return 3
    except (AuthenticationRequiredError, CaptchaRequiredError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 3
    finally:
        password = ""

    console.print(
        Panel.fit(
            "[green]Authenticated successfully.[/green]\n"
            f"Session stored at: {settings.resolved_session_path}\n"
            "Start the MCP server with `vtop-mcp serve`.\n"
            "Only this student's own VTOP account is accessible.",
            title="VTOP login",
        )
    )
    return 0


_MAX_CHALLENGE_ATTEMPTS = 3
_CHALLENGE_RETRY_DELAY = 2.0


async def _fetch_login_challenge(client) -> LoginChallenge:
    """Fetch the login challenge, retrying when VTOP serves its reCAPTCHA variant.

    VTOP flips between its built-in image CAPTCHA and Google reCAPTCHA per
    login-page request; the reCAPTCHA variant cannot be rendered here, but a
    fresh page load frequently offers the built-in image again.
    """
    challenge = await client.initialize()
    for attempt in range(2, _MAX_CHALLENGE_ATTEMPTS + 1):
        if not challenge.requires_browser:
            return challenge
        console.print(
            f"[yellow]VTOP served a browser-based reCAPTCHA challenge (attempt {attempt - 1}); "
            "refreshing the login page…[/yellow]"
        )
        await asyncio.sleep(_CHALLENGE_RETRY_DELAY)
        challenge = await client.initialize()
    return challenge


def _prompt_captcha(challenge, settings: Settings) -> str:
    if challenge.requires_browser:
        console.print(
            "[yellow]VTOP configured a browser-based (Google reCAPTCHA) challenge this time.[/yellow] "
            "The MCP server cannot display it. Please log in once in a browser to obtain a session, "
            "or retry when VTOP offers its built-in image CAPTCHA.",
        )
        raise CaptchaRequiredError("reCAPTCHA challenge cannot be rendered by this terminal.")

    from_env = os.environ.get("VTOP_CAPTCHA", "").strip()
    if from_env:
        return from_env

    image_path = _render_captcha(challenge, settings)
    if image_path is not None:
        console.print(
            f"[cyan]CAPTCHA image saved to[/cyan] {image_path}\n"
            "[cyan]Open it and type the characters below. It is never stored or logged.[/cyan]"
        )
        captcha = input("CAPTCHA: ").strip()
    else:
        console.print("[yellow]VTOP did not return an image CAPTCHA to this client.[/yellow]")
        raise CaptchaRequiredError("No CAPTCHA image could be obtained from VTOP.")
    if not captcha:
        raise CaptchaRequiredError("CAPTCHA value was empty; please try again.")
    return captcha


# ------------------------------------------------------------------ logout
async def _logout(args: argparse.Namespace) -> int:
    settings = _settings()
    client, auth, _metrics, _redactor = _build_stack(settings)
    await auth.bootstrap()
    await auth.dispose()
    await client.close()
    console.print("[yellow]Logged out: in-memory session invalidated and session file removed.[/yellow]")
    return 0


# ------------------------------------------------------------------ status
async def _status(args: argparse.Namespace) -> int:
    settings = _settings()
    client, auth, _metrics, _redactor = _build_stack(settings)
    await auth.bootstrap()
    if auth.session is None:
        console.print("status: no session (run `vtop-mcp login`).")
        await client.close()
        return 1
    alive = await client.check_liveness()
    console.print(f"status: authenticated + session_valid={alive}")
    await client.close()
    return 0 if alive else 1


# ------------------------------------------------------------------ main
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vtop-mcp",
        description="Secure MCP server for the authenticated student's own VIT VTOP account.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Run the MCP server over stdio (default MCP transport).")
    p_login = sub.add_parser("login", help="Bootstrap an authenticated session (manual CAPTCHA).")
    p_login.add_argument("--username", help="VTOP username (prompted if omitted).")
    p_login.add_argument("--password", help="VTOP password. Prefer the prompt; avoid shell history.")
    p_login.add_argument("--no-open", action="store_true", help="Do not auto-open the CAPTCHA image.")
    sub.add_parser("logout", help="Invalidate the session and delete the persisted session file.")
    sub.add_parser("status", help="Show whether an authenticated session exists and is valid.")

    args = parser.parse_args(argv)
    try:
        return asyncio.run(_DISPATCH[args.command](args))
    except KeyboardInterrupt:  # pragma: no cover
        return 130


_DISPATCH = {"serve": _serve, "login": _login, "logout": _logout, "status": _status}


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())