"""Automatic, non-interactive VTOP login for fully automated deployments.

Credentials come from the ``VTOP_USERNAME`` / ``VTOP_PASSWORD`` environment
variables (never from a file). The current login challenge is fetched from
VTOP, the built-in image CAPTCHA is recognized with Tesseract, and the
resulting session is persisted to ``VTOP_SESSION_PATH``. Requires the system
``tesseract`` binary on PATH.

A literal CAPTCHA value can be supplied ahead of time via ``VTOP_CAPTCHA`` to
skip OCR entirely (useful after a manual solve).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
import os
import re

from rich.console import Console
from rich.panel import Panel

from .config import Settings
from .errors import CaptchaRequiredError, InvalidConfigurationError, LoginFailedError, VTopError
from .logging_setup import configure_logging, get_logger
from .metrics import Metrics
from .redaction import Redactor
from .vtop.auth import AuthManager
from .vtop.client import LoginChallenge, VTOPClient

console = Console()
log = get_logger("auto_login")

MAX_CHALLENGE_ATTEMPTS = 3
MAX_LOGIN_ATTEMPTS = 6
CHALLENGE_RETRY_DELAY = 2.0
MIN_CAPTCHA_LEN = 5
CAPTCHA_CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def _load_image(image_bytes: bytes):
    from PIL import Image

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            alpha = image.convert("RGBA").getchannel("A")
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image.convert("RGBA"), mask=alpha)
            gray = background.convert("L")
            return gray.resize((gray.width * 3, gray.height * 3), Image.LANCZOS)
    except Exception:
        return None


def _ocr_guesses(image) -> list[str]:
    import pytesseract

    guesses: list[str] = []
    for psm in ("7", "8"):
        text = pytesseract.image_to_string(
            image,
            config=f"--psm {psm} --oem 3 -c tessedit_char_whitelist={CAPTCHA_CHARSET}",
        )
        cleaned = re.sub(r"[^A-Za-z0-9]", "", text).upper()
        if cleaned:
            guesses.append(cleaned)
    return guesses


def ocr_captcha(image_bytes: bytes) -> str:
    """Return the best-guess text for a VTOP built-in CAPTCHA image."""
    image = _load_image(image_bytes)
    if image is None:
        return ""
    for guess in _ocr_guesses(image):
        if len(guess) >= MIN_CAPTCHA_LEN:
            return guess
    return ""


async def _fetch_image_challenge(client: VTOPClient) -> LoginChallenge:
    challenge = await client.initialize()
    for attempt in range(2, MAX_CHALLENGE_ATTEMPTS + 1):
        if not challenge.requires_browser:
            return challenge
        log.info(
            "VTOP served a browser reCAPTCHA (attempt %d); refreshing login page.", attempt - 1
        )
        await asyncio.sleep(CHALLENGE_RETRY_DELAY)
        challenge = await client.initialize()
    raise CaptchaRequiredError(
        "VTOP configured a browser-based (Google reCAPTCHA) challenge; "
        "automatic OCR cannot proceed."
    )


async def run(settings: Settings, username: str, password: str, manual_captcha: str) -> int:
    configure_logging(settings.log_level)
    redactor = Redactor()
    metrics = Metrics()
    client = VTOPClient(settings, metrics, redactor)
    auth = AuthManager(client, settings, metrics, redactor)
    try:
        for attempt in range(1, MAX_LOGIN_ATTEMPTS + 1):
            try:
                challenge = await _fetch_image_challenge(client)
            except VTopError as exc:
                log.warning(
                    "Could not fetch the login challenge (attempt %d/%d): %s",
                    attempt, MAX_LOGIN_ATTEMPTS, exc,
                )
                continue

            captcha = manual_captcha
            if not captcha:
                try:
                    image_bytes = base64.b64decode(challenge.captcha_image or "")
                except (binascii.Error, ValueError):
                    image_bytes = b""
                captcha = ocr_captcha(image_bytes) if image_bytes else ""
            if len(captcha) < MIN_CAPTCHA_LEN:
                log.info(
                    "No usable CAPTCHA guess on attempt %d; fetching a fresh challenge.", attempt
                )
                continue

            try:
                await auth.login(username, password, captcha, challenge=challenge)
            except LoginFailedError:
                log.info("VTOP rejected the CAPTCHA (attempt %d/%d).", attempt, MAX_LOGIN_ATTEMPTS)
                continue
            except VTopError as exc:
                log.warning("Login attempt %d/%d failed: %s", attempt, MAX_LOGIN_ATTEMPTS, exc)
                continue

            console.print(
                Panel.fit(
                    "[green]Authenticated successfully (automated).[/green]\n"
                    f"Session stored at: {settings.resolved_session_path}\n"
                    "Only this student's own VTOP account is accessible.",
                    title="VTOP login",
                )
            )
            return 0

        console.print(
            f"[red]Automated login failed after {MAX_LOGIN_ATTEMPTS} attempts. "
            "Check VTOP reachability or solve the CAPTCHA manually with `vtop-mcp login`.[/red]"
        )
        return 1
    finally:
        await client.close()


def main(argv=None) -> int:
    try:
        settings = Settings.from_env()
    except InvalidConfigurationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        return 2

    if not settings.enable_login:
        console.print(
            "[red]Login disabled:[/red] set VTOP_ENABLE_LOGIN=true to allow authentication."
        )
        return 2

    username = os.environ.get("VTOP_USERNAME", "").strip()
    password = os.environ.get("VTOP_PASSWORD", "")
    if not username or not password:
        console.print("[red]VTOP_USERNAME and VTOP_PASSWORD must be set for automated login.[/red]")
        return 2

    manual_captcha = os.environ.get("VTOP_CAPTCHA", "").strip()
    return asyncio.run(run(settings, username, password, manual_captcha))


if __name__ == "__main__":
    raise SystemExit(main())