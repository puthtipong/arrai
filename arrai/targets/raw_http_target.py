from __future__ import annotations

"""
RawHTTPTarget — paste a raw HTTP request (Burp-style) as the target.

The request is a complete HTTP/1.1 request string, exactly as captured in
Burp Suite or similar tools.  Use `{PROMPT}` anywhere in the request
(URL, headers, body) as the injection point.

Config example (in target_config.params):
{
    "raw_request": "POST /api/chat HTTP/1.1\\r\\nHost: example.com\\r\\nContent-Type: application/json\\r\\nAuthorization: Bearer TOKEN\\r\\n\\r\\n{\\"message\\": \\"{PROMPT}\\"}",
    "base_url": "https://example.com",    // scheme+host if not in the request line
    "response_path": "reply",             // JSON dot-path extraction (optional)
    "response_regex": "\"text\":\\s*\"([^\"]+)\"",  // regex extraction (optional)
    "timeout": 30,
    "verify_ssl": true
}

The `{PROMPT}` placeholder is substituted with the URL-safe prompt.
For JSON bodies the substitution escapes quotes automatically.
"""

import json
import logging
import re
from typing import TYPE_CHECKING

from arrai.targets.base import Target, TargetCapabilities
from arrai.models.message import Message
from arrai.targets.http_target import _get_nested

if TYPE_CHECKING:
    from arrai.models.session_config import TargetConfig

logger = logging.getLogger(__name__)

_PLACEHOLDER = "{PROMPT}"


def _parse_raw_request(raw: str) -> dict:
    """
    Parse a raw HTTP/1.1 request string into its components.

    Returns:
        {
            "method": "POST",
            "path": "/api/chat",
            "http_version": "HTTP/1.1",
            "headers": {"Host": "example.com", ...},
            "body": '{"message": "{PROMPT}"}',
        }
    """
    # Normalise line endings
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    # Split header section from body at first blank line
    if "\n\n" in raw:
        header_section, body = raw.split("\n\n", 1)
    else:
        header_section, body = raw, ""

    lines = header_section.split("\n")
    if not lines:
        raise ValueError("Empty raw HTTP request")

    # Parse request line
    request_line = lines[0].strip()
    parts = request_line.split(" ", 2)
    if len(parts) < 2:
        raise ValueError(f"Malformed request line: {request_line!r}")
    method = parts[0].upper()
    path = parts[1]
    http_version = parts[2] if len(parts) > 2 else "HTTP/1.1"

    # Parse headers
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            name, _, value = line.partition(":")
            headers[name.strip()] = value.strip()

    return {
        "method": method,
        "path": path,
        "http_version": http_version,
        "headers": headers,
        "body": body,
    }


class RawHTTPTarget(Target):
    """
    Executes a raw HTTP request (Burp-style) with `{PROMPT}` substitution.

    Stateful: maintains a persistent httpx client with cookie jar.
    """

    _CAPABILITIES = TargetCapabilities(
        is_stateful=True,
        supports_system_prompt=False,
        supports_multi_turn=True,
    )

    def __init__(self, config: "TargetConfig") -> None:
        super().__init__(config)
        p = config.params

        raw_request = p.get("raw_request", "")
        if not raw_request:
            raise ValueError("raw_http target requires 'raw_request' in params")

        self._parsed = _parse_raw_request(raw_request)
        self._base_url: str = p.get("base_url", "").rstrip("/")
        self._response_path: str | None = p.get("response_path")
        self._response_regex: str | None = p.get("response_regex")
        self._timeout: float = float(p.get("timeout", 30))
        self._verify_ssl: bool = bool(p.get("verify_ssl", True))
        self._client = None

    # ------------------------------------------------------------------
    # Target interface
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> TargetCapabilities:
        return self._CAPABILITIES

    @property
    def target_id(self) -> str:
        host = self._parsed["headers"].get("Host", self._base_url)
        return f"raw_http:{host}{self._parsed['path'][:40]}"

    async def send_async(
        self,
        message: str,
        conversation_history=None,
        system_prompt: str | None = None,
    ) -> Message:
        client = await self._get_client()
        parsed = self._parsed

        # Build full URL
        host = parsed["headers"].get("Host", "")
        if self._base_url:
            base = self._base_url
        elif host:
            scheme = "https"
            base = f"{scheme}://{host}"
        else:
            raise ValueError("Cannot determine target URL: set 'base_url' in params")

        # Substitute {PROMPT} in path, body, and header values
        # For JSON bodies, escape the prompt first
        escaped = message.replace("\\", "\\\\").replace('"', '\\"')

        def substitute(text: str) -> str:
            # Try JSON-safe substitution in the body; raw substitution elsewhere
            return text.replace(_PLACEHOLDER, escaped)

        path = substitute(parsed["path"])
        url = base + path

        headers = {k: substitute(v) for k, v in parsed["headers"].items()}
        body = substitute(parsed["body"])

        try:
            resp = await client.request(
                method=parsed["method"],
                url=url,
                headers=headers,
                content=body.encode("utf-8") if body else None,
                extensions={"http2": parsed["http_version"] == "HTTP/2"},
            )
            resp.raise_for_status()
            response_text = self._extract_response(resp.text)
            return Message(
                role="assistant",
                content=response_text,
                metadata={"status_code": resp.status_code},
            )

        except Exception as exc:
            logger.warning("RawHTTPTarget error: %s", exc)
            return Message(
                role="assistant",
                content=f"[HTTP error: {exc}]",
                metadata={"error": str(exc)},
            )

    async def reset_async(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_client(self):
        if self._client is None:
            try:
                import httpx
            except ImportError as exc:
                raise ImportError(
                    "httpx is required for raw_http targets. "
                    "Install it with: pip install httpx"
                ) from exc
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=self._timeout,
                verify=self._verify_ssl,
            )
        return self._client

    def _extract_response(self, text: str) -> str:
        if self._response_path:
            try:
                data = json.loads(text)
                return _get_nested(data, self._response_path)
            except Exception:
                return text
        if self._response_regex:
            m = re.search(self._response_regex, text, re.DOTALL)
            if m:
                return m.group(1) if m.lastindex else m.group(0)
        try:
            data = json.loads(text)
            return str(data) if isinstance(data, str) else json.dumps(data, indent=2)
        except Exception:
            return text
