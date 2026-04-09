from __future__ import annotations

"""
PlaywrightTarget — browser-based target for web UIs without HTTP APIs.

Use this when the application is only accessible through a web interface
(chat widgets, web forms, consumer AI products, etc.).

Requires: pip install playwright && playwright install chromium

Config example (in target_config.params):
{
    "url": "https://example.com/chat",

    // CSS selector for the text input / textarea
    "input_selector": "textarea#chat-input",

    // CSS selector for the submit button (optional — if omitted, presses Enter)
    "submit_selector": "button[aria-label='Send']",

    // CSS selector for the last assistant response element
    "response_selector": ".message.assistant:last-of-type",

    // How to detect when the response is ready (default: "idle")
    //   "idle"        — waits for network to go idle after submitting
    //   "new_element" — waits for a new element matching response_selector to appear
    //   "fixed"       — waits a fixed number of milliseconds
    "wait_strategy": "idle",

    // For wait_strategy="fixed": how long to wait in ms (default 3000)
    "wait_ms": 3000,

    // For wait_strategy="new_element": timeout in ms (default 10000)
    "element_timeout_ms": 10000,

    // Clear the input field before typing (default true)
    "clear_input": true,

    // Run browser in headless mode (default true; set false for debugging)
    "headless": true,

    // Slow down interactions by N ms (useful for debugging)
    "slow_mo": 0,

    // Browser viewport
    "viewport_width": 1280,
    "viewport_height": 800
}
"""

import asyncio
import logging
from typing import TYPE_CHECKING

from arrai.targets.base import Target, TargetCapabilities
from arrai.models.message import Message

if TYPE_CHECKING:
    from arrai.models.session_config import TargetConfig

logger = logging.getLogger(__name__)


class PlaywrightTarget(Target):
    """
    Interacts with a web UI using Playwright browser automation.

    Stateful: the browser session persists across turns.
    reset_async() navigates back to the initial URL (new browser context).

    The approach is CSS-selector-based: specify where to type, where to
    click, and where to read the response.  For unusual UIs, you can also
    pass `interaction_script` (a path to a Python file) that defines an
    async `interact(page, prompt: str) -> str` function — this gives you
    full control over browser interactions.
    """

    _CAPABILITIES = TargetCapabilities(
        is_stateful=True,
        supports_system_prompt=False,
        supports_multi_turn=True,
    )

    def __init__(self, config: "TargetConfig") -> None:
        super().__init__(config)
        p = config.params

        self._url: str = p["url"]
        self._input_selector: str = p.get("input_selector", "textarea")
        self._submit_selector: str | None = p.get("submit_selector")
        self._response_selector: str = p.get("response_selector", ".message:last-of-type")

        self._wait_strategy: str = p.get("wait_strategy", "idle")
        self._wait_ms: int = int(p.get("wait_ms", 3000))
        self._element_timeout_ms: int = int(p.get("element_timeout_ms", 10000))

        self._clear_input: bool = bool(p.get("clear_input", True))
        self._headless: bool = bool(p.get("headless", True))
        self._slow_mo: int = int(p.get("slow_mo", 0))
        self._viewport_width: int = int(p.get("viewport_width", 1280))
        self._viewport_height: int = int(p.get("viewport_height", 800))

        # Optional: path to custom interaction script
        self._interaction_script: str | None = p.get("interaction_script")
        self._custom_interact = None  # loaded lazily

        # Browser lifecycle objects
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    # ------------------------------------------------------------------
    # Target interface
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> TargetCapabilities:
        return self._CAPABILITIES

    @property
    def target_id(self) -> str:
        return f"playwright:{self._url}"

    async def send_async(
        self,
        message: str,
        conversation_history=None,
        system_prompt: str | None = None,
    ) -> Message:
        page = await self._get_page()
        try:
            response_text = await self._interact(page, message)
            return Message(
                role="assistant",
                content=response_text,
                metadata={"url": self._url},
            )
        except Exception as exc:
            logger.warning("PlaywrightTarget interaction error: %s", exc)
            return Message(
                role="assistant",
                content=f"[Browser error: {exc}]",
                metadata={"error": str(exc)},
            )

    async def reset_async(self) -> None:
        """Drop the browser context and start fresh."""
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        self._page = None
        self._context = None
        # Keep browser instance; just reset context/page

    # ------------------------------------------------------------------
    # Browser management
    # ------------------------------------------------------------------

    async def _get_page(self):
        """Get (or create) the Playwright page, navigating to the target URL."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:
            raise ImportError(
                "playwright is required for playwright targets.\n"
                "Install it with:\n"
                "    pip install playwright\n"
                "    playwright install chromium"
            ) from exc

        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                slow_mo=self._slow_mo,
            )

        if self._page is None or self._context is None:
            self._context = await self._browser.new_context(
                viewport={"width": self._viewport_width, "height": self._viewport_height},
            )
            self._page = await self._context.new_page()
            await self._page.goto(self._url, wait_until="domcontentloaded")
            logger.info("PlaywrightTarget: navigated to %s", self._url)

        return self._page

    async def _interact(self, page, prompt: str) -> str:
        """Type the prompt, submit, and extract the response."""

        # ── Custom interaction script ──────────────────────────────────
        if self._interaction_script:
            return await self._run_custom_script(page, prompt)

        # ── Default: type → submit → wait → extract ───────────────────

        # 1. Count current response elements (for new_element detection)
        prev_count = 0
        if self._wait_strategy == "new_element":
            prev_count = await page.locator(self._response_selector).count()

        # 2. Clear + type
        input_el = page.locator(self._input_selector).last
        await input_el.wait_for(state="visible", timeout=10000)
        if self._clear_input:
            await input_el.fill("")
        await input_el.type(prompt, delay=20)

        # 3. Submit
        if self._submit_selector:
            await page.locator(self._submit_selector).click()
        else:
            await input_el.press("Enter")

        # 4. Wait for response
        if self._wait_strategy == "idle":
            await page.wait_for_load_state("networkidle", timeout=self._element_timeout_ms)
        elif self._wait_strategy == "new_element":
            # Poll until a new response element appears
            deadline = asyncio.get_event_loop().time() + self._element_timeout_ms / 1000
            while asyncio.get_event_loop().time() < deadline:
                count = await page.locator(self._response_selector).count()
                if count > prev_count:
                    break
                await asyncio.sleep(0.3)
        elif self._wait_strategy == "fixed":
            await asyncio.sleep(self._wait_ms / 1000)

        # 5. Extract response text
        response_els = page.locator(self._response_selector)
        count = await response_els.count()
        if count == 0:
            return "(no response element found)"
        last_el = response_els.nth(count - 1)
        return (await last_el.inner_text()).strip()

    async def _run_custom_script(self, page, prompt: str) -> str:
        """
        Load and call a user-provided interaction script.

        The script must define:
            async def interact(page, prompt: str) -> str: ...
        """
        if self._custom_interact is None:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "_pw_interact", self._interaction_script
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore
            if not hasattr(mod, "interact"):
                raise ValueError(
                    f"interaction_script {self._interaction_script!r} must define "
                    "async def interact(page, prompt: str) -> str"
                )
            self._custom_interact = mod.interact

        return await self._custom_interact(page, prompt)

    def __del__(self):
        """Best-effort cleanup (sync teardown not available in __del__)."""
        if self._browser:
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.run_until_complete(self._browser.close())
                    loop.run_until_complete(self._playwright.stop())
            except Exception:
                pass
