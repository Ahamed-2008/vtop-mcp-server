from __future__ import annotations

from playwright.sync_api import BrowserContext, Page, Request, Response

from vtop_discovery.capture.requests import capture_request
from vtop_discovery.capture.responses import capture_response
from vtop_discovery.storage.models import CapturedExchange
from vtop_discovery.utils.logging import get_logger

logger = get_logger(__name__)


class NetworkCapture:
    """Attach Playwright request/response listeners on a browser context and its pages."""

    def __init__(self, context: BrowserContext) -> None:
        self._context = context
        self._pending: dict[Request, CapturedExchange] = {}
        self.exchanges: list[CapturedExchange] = []
        self.active_purpose: str | None = None
        self._attached = False

    def start_phase(self, purpose: str) -> None:
        """Tag captured requests during this phase with an explicit purpose."""
        self.active_purpose = purpose
        logger.info("Started discovery phase: %s", purpose)

    def stop_phase(self) -> None:
        """Clear active phase purpose tag."""
        logger.info("Stopped discovery phase: %s", self.active_purpose)
        self.active_purpose = None

    def attach(self) -> None:
        if self._attached:
            return
        self._attached = True
        self._context.on("request", self._on_request)
        self._context.on("response", self._on_response)
        self._context.on("page", self._on_new_page)

        for page in self._context.pages:
            self.attach_page(page)

        logger.info("Network capture attached to context and existing pages")

    def attach_page(self, page: Page) -> None:
        try:
            page.on("request", self._on_request)
            page.on("response", self._on_response)
        except Exception as exc:
            logger.debug("Could not attach listeners to page: %s", exc)

    def detach(self) -> None:
        if not self._attached:
            return
        self._attached = False
        try:
            self._context.remove_listener("request", self._on_request)
            self._context.remove_listener("response", self._on_response)
            self._context.remove_listener("page", self._on_new_page)
        except Exception:
            pass

    def _on_new_page(self, page: Page) -> None:
        logger.info("New page/tab detected; attaching network capture")
        self.attach_page(page)

    def _on_request(self, request: Request) -> None:
        if request in self._pending:
            return
        purpose = self.active_purpose or "unknown"
        captured = CapturedExchange(request=capture_request(request), purpose=purpose)
        self._pending[request] = captured
        self.exchanges.append(captured)

    def _on_response(self, response: Response) -> None:
        request = response.request
        snapshot = capture_response(response)
        captured = self._pending.get(request)
        if captured is None:
            purpose = self.active_purpose or "unknown"
            captured = CapturedExchange(
                request=capture_request(request),
                response=snapshot,
                purpose=purpose,
            )
            self._pending[request] = captured
            self.exchanges.append(captured)
            return
        captured.response = snapshot
