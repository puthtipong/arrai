from __future__ import annotations

"""
CustomHTTPTarget — send prompts to any HTTP endpoint.

Covers REST chatbot APIs, custom AI backends, and any service reachable
via HTTP that accepts a prompt and returns a response.

Config example (in target_config.params):
{
    "url": "https://api.example.com/v1/chat",
    "method": "POST",

    // Structured body: leaf string values containing "{prompt}" are substituted.
    // Sent as JSON.
    "body": {
        "message": "{prompt}",
        "session_id": "arrai-test"
    },

    // OR: raw template string (sent with content_type; default application/json)
    // "body_template": "{\"query\": \"{prompt}\"}",

    // OR: HTML form data
    // "form_data": {"q": "{prompt}"},

    // Response extraction: dot-path into JSON  e.g. "choices[0].message.content"
    "response_path": "response",

    // OR: regex with a capture group
    // "response_regex": "\"text\":\\s*\"([^\"]+)\"",

    "headers": {
        "Authorization": "Bearer TOKEN",
        "X-Api-Key": "abc123"
    },

    // Starting cookies
    "cookies": {},

    // Content-Type for raw body_template (default: application/json)
    "content_type": "application/json",

    // HTTP timeout in seconds
    "timeout": 30
}
"""

import json
import logging
import re
import os
from typing import TYPE_CHECKING

from arrai.targets.base import Target, TargetCapabilities
from arrai.models.message import Message

if TYPE_CHECKING:
    from arrai.models.session_config import TargetConfig

logger = logging.getLogger(__name__)


def _get_nested(data: object, path: str) -> str:
    """
    Navigate a dot-path with optional array indices.

    Examples:
        "response"                       → data["response"]
        "choices[0].message.content"    → data["choices"][0]["message"]["content"]
        "data.items[2].text"            → data["data"]["items"][2]["text"]
    """
    parts = re.split(r"\[(\d+)\]|(\.)(?!\d)", path)
    for part in parts:
        if part is None or part == ".":
            continue
        if part.isdigit():
            data = data[int(part)]  # type: ignore[index]
        elif part:
            data = data[part]  # type: ignore[index]
    return str(data)


def _substitute_prompt(obj: object, prompt: str) -> object:
    """
    Recursively substitute "{prompt}" in any string leaf of a dict/list/str.
    """
    if isinstance(obj, str):
        return obj.replace("{prompt}", prompt)
    if isinstance(obj, dict):
        return {k: _substitute_prompt(v, prompt) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_prompt(item, prompt) for item in obj]
    return obj


class CustomHTTPTarget(Target):
    """
    Sends prompts to a custom HTTP endpoint and extracts the response.

    Stateful: maintains a persistent httpx client with cookie jar so the
    server can track session state across turns.  Call reset_async() to
    drop the session and start fresh.
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
        self._method: str = p.get("method", "POST").upper()

        # Body spec: one of body (dict), body_template (str), or form_data (dict)
        self._body_dict: dict | None = p.get("body")
        self._body_template: str | None = p.get("body_template")
        self._form_data: dict | None = p.get("form_data")

        # Response extraction
        self._response_path: str | None = p.get("response_path")
        self._response_regex: str | None = p.get("response_regex")

        self._headers: dict = p.get("headers", {})
        self._cookies: dict = p.get("cookies", {})
        self._content_type: str = p.get("content_type", "application/json")
        self._timeout: float = float(p.get("timeout", 30))

        self._client = None  # httpx.AsyncClient, lazy-created

    # ------------------------------------------------------------------
    # Target interface
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> TargetCapabilities:
        return self._CAPABILITIES

    @property
    def target_id(self) -> str:
        return f"custom_http:{self._url}"

    async def send_async(
        self,
        message: str,
        conversation_history=None,
        system_prompt: str | None = None,
    ) -> Message:
        client = await self._get_client()

        try:
            if self._body_dict is not None:
                # Structured JSON body with {prompt} substitution
                body = _substitute_prompt(self._body_dict, message)
                resp = await client.request(
                    method=self._method,
                    url=self._url,
                    json=body,
                )
            elif self._body_template is not None:
                # Raw string template
                body_str = self._body_template.replace("{prompt}", message)
                headers = dict(self._headers)
                headers.setdefault("Content-Type", self._content_type)
                resp = await client.request(
                    method=self._method,
                    url=self._url,
                    content=body_str.encode("utf-8"),
                    headers=headers,
                )
            elif self._form_data is not None:
                # HTML form data
                form = {k: v.replace("{prompt}", message) for k, v in self._form_data.items()}
                resp = await client.request(
                    method=self._method,
                    url=self._url,
                    data=form,
                )
            else:
                # Plain text
                resp = await client.request(
                    method=self._method,
                    url=self._url,
                    content=message.encode("utf-8"),
                )

            resp.raise_for_status()
            response_text = self._extract_response(resp.text)

            return Message(
                role="assistant",
                content=response_text,
                metadata={
                    "status_code": resp.status_code,
                    "url": self._url,
                },
            )

        except Exception as exc:
            logger.warning("CustomHTTPTarget error: %s", exc)
            return Message(
                role="assistant",
                content=f"[HTTP error: {exc}]",
                metadata={"error": str(exc)},
            )

    async def reset_async(self) -> None:
        """Drop the HTTP session (cookies cleared) and start fresh."""
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
                    "httpx is required for custom_http targets. "
                    "Install it with: pip install httpx"
                ) from exc
            self._client = httpx.AsyncClient(
                headers=self._headers,
                cookies=self._cookies,
                follow_redirects=True,
                timeout=self._timeout,
            )
        return self._client

    def _extract_response(self, text: str) -> str:
        """Extract the response string from the raw HTTP response body."""
        if self._response_path:
            try:
                data = json.loads(text)
                return _get_nested(data, self._response_path)
            except Exception as exc:
                logger.debug("JSON path extraction failed (%s), returning raw body", exc)
                return text

        if self._response_regex:
            m = re.search(self._response_regex, text, re.DOTALL)
            if m:
                return m.group(1) if m.lastindex else m.group(0)
            return text

        # No extraction spec — return the raw body
        # Try to pretty-print JSON, fall back to raw text
        try:
            data = json.loads(text)
            if isinstance(data, str):
                return data
            return json.dumps(data, indent=2)
        except Exception:
            return text
