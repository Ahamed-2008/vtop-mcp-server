# VTOP endpoint map

This is the single documentation of **which VTOP HTTP endpoints the server
uses**, why, and how each MCP tool maps to them. It mirrors the live-discovered
behaviour (see `vtop-endpoint-discovery/` in the repository root for the raw
captures) and `src/vtop_mcp/vtop/endpoints.py` is the machine-readable source
of truth.

Paths are relative to `VTOP_BASE_URL`.

## Authentication flow (session establishment)

| Step | Method | Path | Purpose |
| --- | --- | --- | --- |
| 1 | GET | `/vtop/open/page` | Auth portal; carries the login `_csrf` |
| 2 | POST | `/vtop/prelogin/setup` | Initializes the auth environment (form field `flag=VTOP`, `_csrf`); redirects to `/vtop/init/page` |
| 3 | GET | `/vtop/init/page` | Redirect bootstrap → `/vtop/login` (or `/vtop/main/page` when already authenticated) |
| 4 | GET | `/vtop/login` | Renders the login form; exposes a fresh `_csrf` and the manual CAPTCHA image (or reCAPTCHA) |
| 5 | POST | `/vtop/login` | Sends `username`, `password`, `captchaStr`, `_csrf` (manual CAPTCHA; never bypassed) |
| 6 | GET | `/vtop/main/page` | Authenticated app frame → redirects to `/vtop/open` |
| 7 | GET | `/vtop/open` | Navigates to the dashboard container |
| 8 | GET | `/vtop/content` | Dashboard; embeds `var csrfValue`, `var id`, hidden `authorizedID` / `authorizedIDX` inputs. **Success marker for login and the source of the session's `authorizedID` + CSRF.** |

> The session liveness probe re-GETs `/vtop/content`; a redirect to `/vtop/login`
> there means the session expired.

## Read-only data endpoints

| Method | Path | Parser | Cached | Notes |
| --- | --- | --- | --- | --- |
| POST | `/vtop/get/dashboard/current/cgpa/credits` | `CGPAParser` | yes | `<ul class="list-group">` rows: "Total Credits Required :", "Earned Credits :", "Current CGPA :" |
| POST | `/vtop/get/dashboard/current/semester/course/details` | `CourseParser` | yes | Table [#, Code - Course Name, Type, Attendance %, Remarks]; semester badge span (e.g. `FALLSEM2026-27`) |
| POST | `/vtop/get/upcoming/digital/assignments` | `AssignmentParser` | yes | Table [#, Course Name, Title, Last Date, Uploaded]; dates DD-MM-YYYY |
| POST | `/vtop/get/scheduled/events` | `EventParser` | yes | Day cards (day + month), section labels ("Today : Ongoing Events" / "Forthcoming Events"), title/category/date/organizer |
| POST | `/vtop/get/last/five/feedbacks` | `FeedbackParser` | yes | Table [#, Feedback, Category, Status] |
| POST | `/vtop/get/dashboard/proctor/message` | `ProctorParser` | no | May legitimately return whitespace (no message) |

All data endpoints are POSTs authenticated with the session's `_csrf` +
`authorizedID` + `x` timestamp.

## Tool → endpoint → parser mapping

| MCP tool | VTOP endpoint(s) | Parser / model |
| --- | --- | --- |
| `get_cgpa` | CGPA_CREDITS | `CGPAParser` → `CGPA` |
| `get_current_courses` | COURSE_DETAILS | `CourseParser` → `CourseList` |
| `get_attendance` | COURSE_DETAILS (cached) | derived from `CourseList` rows |
| `get_marks` | COURSE_DETAILS | availability report only (no marks columns in the captured response) |
| `get_academic_summary` | CGPA_CREDITS + COURSE_DETAILS | `CGPAComposite` |
| `get_assignments` | ASSIGNMENTS | `AssignmentParser` → `AssignmentList` |
| `get_events` | EVENTS | `EventParser` → `EventList` |
| `get_feedback` | FEEDBACKS | `FeedbackParser` → `FeedbackList` |
| `get_proctor_message` | PROCTOR_MESSAGE | `ProctorParser` → `ProctorMessage` |
| `get_session_status` | CONTENT (liveness) | `SessionStatus` |

## Support endpoints (discovered, not used by any tool)

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/vtop/login/checkusername` | Username/session validation (captured as `/vtop/login/checkUserName`) |
| POST | `/vtop/admissions/doGetPassedOutInformationMandatory` | Passed-out information/status check |

## If VTOP changes

Parsers raise a stable `VTOP_PARSE_ERROR` / `CSRF_ERROR` (never a guessed
value) and the failure is surfaced as an MCP JSON-RPC error. To re-anchor the
server, refresh the sanitized captures in `tests/fixtures/*.html`, update the
affected parser, and run the suite — `test_parsers.py` asserts the exact values
seen in the real responses.