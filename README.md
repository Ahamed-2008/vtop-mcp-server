# vtop-mcp-server

A secure **Model Context Protocol (MCP)** server that gives an AI assistant a
**read-only**, structured interface to **the authenticated student's own VIT
VTOP account**.

- **Read-only.** Only GET (pages) and POST (read-only data queries) requests
  are made. No tool can create, submit, or mutate anything in VTOP.
- **Manual CAPTCHA only.** VTOP requires a CAPTCHA at login. This server never
  bypasses it — a human solves it once during `vtop-mcp login` (see Security).
- **Own-account only.** Every data request is bound to the session's
  `authorizedID`, which is extracted from VTOP itself and can never be
  supplied by a caller.
- **Grounded in real VTOP responses.** Parsers are built against sanitized
  captures of the live site (`tests/fixtures/*.html`). They never invent data
  that VTOP does not provide (e.g. VTOP's current-credits endpoint has no GPA;
  the CGPA tool omits it).

## Tools

| Tool | Returns |
| --- | --- |
| `get_academic_summary` | CGPA, earned/required credits, semester label, courses with attendance |
| `get_cgpa` | Current CGPA, earned credits, total credits required |
| `get_current_courses` | Course code, name, type, attendance %/remark per course |
| `get_attendance` | Per-course attendance percentages + remarks (reuses cached course data) |
| `get_marks` | Marks availability report (captured endpoint exposes attendance/remarks only) |
| `get_assignments` | Upcoming digital assignments (course, title, last date) |
| `get_events` | Scheduled events grouped by day (title, category, date, organizer) |
| `get_feedback` | Last five feedback entries (feedback, category, status) |
| `get_proctor_message` | Dashboard proctor message, if any |
| `get_session_status` | Whether a valid authenticated session exists |

All tools take no arguments and are idempotent. Errors are returned as JSON-RPC
errors with a stable code (e.g. `AUTHENTICATION_REQUIRED`, `SESSION_EXPIRED`,
`VTOP_UNAVAILABLE`) in `error.data`.

## Requirements

- Python 3.11+ (developed on 3.14)
- An internet connection to `https://vtop.vit.ac.in` (or `VTOP_BASE_URL`)

## Install

```bash
python -m venv .venv
.venv/bin/pip install -e .
```

## Authenticate (one time; manual CAPTCHA)

```bash
vtop-mcp login            # prompts username + hidden password, shows CAPTCHA image
```

The CAPTCHA image is written to a 0600 temp file and auto-opened if
`xdg-open`/`open` is available (use `--no-open` otherwise). You type the
characters you see; the value is never stored or logged. On success the session
(cookies + CSRF + `authorizedID`) is persisted to
`.vtop-session/session.json` with `0600` permissions.

## Run the MCP server

```bash
vtop-mcp serve
```

This serves MCP **stdio** — the standard transport used by Claude Desktop,
opencode, and others.

Example MCP client configuration (opencode / Claude Desktop):

```json
{
  "mcpServers": {
    "vtop": {
      "command": "/absolute/path/to/vtop-mcp",
      "args": ["serve"]
    }
  }
}
```

## Other commands

```bash
vtop-mcp status    # is there a session, and is it valid against VTOP?
vtop-mcp logout    # invalidate the in-memory session and delete the session file
```

## Configuration (environment variables)

All optional; defaults in parentheses.

| Variable | Purpose | Default |
| --- | --- | --- |
| `VTOP_BASE_URL` | VTOP origin (no trailing slash) | `https://vtop.vit.ac.in` |
| `VTOP_INITIAL_URL` | Auth entry page (path only) | `/vtop/open/page` |
| `VTOP_ENABLE_LOGIN` | Allow the interactive login flow | `true` |
| `VTOP_SESSION_PATH` | Where the session file is stored | `.vtop-session/session.json` |
| `VTOP_SESSION_TTL` | TTL (s) after which a liveness probe is forced | `3600` |
| `VTOP_CACHE_TTL` | TTL (s) for cached read-only data | `120` |
| `VTOP_TIMEOUT_CONNECT/READ/WRITE/POOL` | httpx timeouts (s) | `10/30/10/10` |
| `VTOP_RETRY_ATTEMPTS` | Transient-error retries (auth reqs never retried) | `2` |
| `VTOP_REQUEST_RATE` | Approx. max requests/sec toward VTOP | `2` |
| `VTOP_LOG_LEVEL` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` | `INFO` |
| `VTOP_USERNAME` / `VTOP_CAPTCHA` | Non-interactive login (testing only) | unset |

**Never** put a password in `.env` or environment variables.

## Security model

- **Manual CAPTCHA is a deliberate boundary** — VTOP login is impossible
  without a human solving it; the server keeps it that way. There is
  **no CAPTCHA bypass, solver, or token reuse** anywhere. A session expires and
  the operator re-runs `vtop-mcp login`.
- **Secrets are never logged.** A logging `Redactor` masks CSRF tokens, UUIDs,
  cookies, `authorizedID`, the username, `Authorization`/`Cookie` headers, and
  CAPTCHA values. See `vtop_mcp/redaction.py`.
- **The session is the source of truth.** `authorizedID` and CSRF come from the
  bound session (extracted from VTOP), never from tool callers, so an MCP
  client cannot ask the server to act for another account.
- **Persistence is 0600 and expiring.** Session files are written with
  ownership-only permissions and have a hard 6‑hour maximum age.
- **Login may be disabled** with `VTOP_ENABLE_LOGIN=false`, in which case only a
  previously established session can be used.
- **Rate limiting + retries** protect VTOP; authentication requests are never
  retried and authorization rejection is detected eagerly (a `/vtop/login`
  redirect on a data query maps to `SESSION_EXPIRED`).

## Development

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -q        # 120 tests
```

The test suite runs against a **mock VTOP server** (`mock_vtop/server.py`) that
reproduces the discovered auth flow (pre-login chain, manual CAPTCHA, session
cookies/CSRF) and serves the real sanitized fixtures. It is also runnable
standalone for manual testing:

```bash
.venv/bin/python -m mock_vtop.server    # http://127.0.0.1:8734 (captcha=K7M2P9)
```

## Layout

```
src/vtop_mcp/
  cli.py                  # serve / login / logout / status
  config.py               # env-driven settings
  errors.py               # stable, secret-free error codes
  redaction.py            # secret masking for logs
  logging_setup.py        # app logger + correlation ids
  metrics.py              # aggregate, privacy-conscious counters
  models/                 # typed pydantic outputs (VTOP-faithful)
  vtop/
    endpoints.py          # single source of truth for VTOP routes
    csrf.py              # token extraction/validation
    session.py           # session state + secure persistence
    client.py            # httpx client, CSRF-aware auth, expiry detection
    auth.py              # session manager (manual login, dispose)
    cache.py             # TTL cache scoped per authorizedID
    parsers/             # cgpa, courses, assignments, events, feedback, proctor
  services/academic.py    # service layer over client + parsers + cache
  server/
    schemas.py            # tool output models
    tools.py             # tool specs + error mapping
    mcp_server.py        # MCP transport wiring (stdio)
mock_vtop/server.py       # local mock VTOP server for dev/tests
tests/                    # unit + integration + end-to-end MCP tests
docs/vtop-endpoints.md    # discovered endpoint map (tool → endpoint → parser)
```

## Limitations (faithful to VTOP)

- VTOP's current-credits endpoint does **not** expose a GPA — the CGPA tool
  reports CGPA and credits only.
- The course-details endpoint exposes attendance % + remarks, **not** marks or
  assessment components — `get_marks` reports availability explicitly rather
  than fabricating data.
- The proctor-message endpoint can legitimately return nothing.

## License

MIT