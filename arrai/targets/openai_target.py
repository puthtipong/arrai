from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from arrai.targets.base import Target, TargetCapabilities

if TYPE_CHECKING:
    from arrai.models.message import Message
    from arrai.models.session_config import TargetConfig


class OpenAITarget(Target):
    """
    Stateless OpenAI chat target.

    params (in TargetConfig.params):
        model          str   e.g. "gpt-4o", "gpt-5.4"          (required)
        api_key_env    str   env var holding the API key         (default: OPENAI_API_KEY)
        system_prompt  str   system prompt for the target LLM   (optional)
        temperature    float                                     (default: 0.7)
        base_url       str   override for Azure/local proxies   (optional)
    """

    def __init__(self, config: "TargetConfig") -> None:
        super().__init__(config)
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise ImportError("openai package required: pip install openai") from e

        api_key_env = config.params.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise EnvironmentError(
                f"OpenAI API key not found. Set the {api_key_env!r} environment variable."
            )

        kwargs: dict = {"api_key": api_key}
        if base_url := config.params.get("base_url"):
            kwargs["base_url"] = base_url

        self._client = AsyncOpenAI(**kwargs)
        self._model = config.params.get("model", "gpt-4o")
        self._system_prompt: str | None = config.params.get("system_prompt")
        self._temperature: float = float(config.params.get("temperature", 0.7))

    # ------------------------------------------------------------------
    # Target interface
    # ------------------------------------------------------------------

    @property
    def capabilities(self) -> TargetCapabilities:
        return TargetCapabilities(
            is_stateful=False,
            supports_system_prompt=True,
            supports_multi_turn=True,
        )

    async def send_async(
        self,
        message: str,
        conversation_history: list["Message"] | None = None,
        system_prompt: str | None = None,
    ) -> "Message":
        from arrai.models.message import Message

        # Build message list for the API
        api_messages: list[dict] = []

        # System prompt: prefer call-time override, then instance default
        effective_system = system_prompt or self._system_prompt
        if effective_system:
            api_messages.append({"role": "system", "content": effective_system})

        # Prior turns
        if conversation_history:
            for m in conversation_history:
                # Skip system messages from history — we've already added ours
                if m.role != "system":
                    api_messages.append(m.to_api_dict())

        # Current user turn
        api_messages.append({"role": "user", "content": message})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            temperature=self._temperature,
        )

        content = response.choices[0].message.content or ""
        return Message(
            role="assistant",
            content=content,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "model": self._model,
                "finish_reason": response.choices[0].finish_reason,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                } if response.usage else {},
            },
        )

    async def reset_async(self) -> None:
        # Stateless — nothing to reset
        pass

    @property
    def target_id(self) -> str:
        return f"openai:{self._model}"
