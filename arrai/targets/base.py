from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arrai.models.message import Message
    from arrai.models.session_config import TargetConfig


@dataclass
class TargetCapabilities:
    """Declares what a target supports."""

    is_stateful: bool
    # True  → web app / application: maintains its own session state.
    #         send_async ignores conversation_history; use reset_async() to clear.
    # False → raw LLM: stateless. Pass full conversation_history each call.

    supports_system_prompt: bool
    supports_multi_turn: bool
    input_modalities: list[str] = field(default_factory=lambda: ["text"])
    output_modalities: list[str] = field(default_factory=lambda: ["text"])
    max_turns: int | None = None  # None = unlimited


class Target(ABC):
    """
    Abstract base for all ArrAI targets.

    Stateless targets (is_stateful=False, e.g. raw LLMs):
        - receive full conversation_history on each call
        - reset_async() is a no-op

    Stateful targets (is_stateful=True, e.g. Playwright web apps):
        - conversation_history is ignored; they maintain internal session state
        - reset_async() clears session state for a fresh conversation
        - backtracking requires reset + replay of retained prefix
    """

    def __init__(self, config: "TargetConfig") -> None:
        self._config = config

    @property
    def target_id(self) -> str:
        """Stable identifier used in conversation traces."""
        return f"{self._config.target_type}"

    @property
    @abstractmethod
    def capabilities(self) -> TargetCapabilities: ...

    @abstractmethod
    async def send_async(
        self,
        message: str,
        conversation_history: list["Message"] | None = None,
        system_prompt: str | None = None,
    ) -> "Message":
        """
        Send a prompt and return the target's response as a Message.

        Args:
            message:              The user-turn content to send.
            conversation_history: For stateless targets — the full prior
                                  conversation (list[Message]). Ignored by
                                  stateful targets.
            system_prompt:        Optional system prompt. Only used by targets
                                  that support_system_prompt. For stateless
                                  targets this is applied on every call; for
                                  stateful targets only on the first call or
                                  after reset_async().
        """
        ...

    @abstractmethod
    async def reset_async(self) -> None:
        """
        Clear all session state.

        Stateful targets: end the current session, ready for fresh conversation.
        Stateless targets: no-op.
        """
        ...
