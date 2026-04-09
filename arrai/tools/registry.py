from __future__ import annotations

"""
ToolRegistry: wires tool schemas to async handler functions.

GarakAgent holds a ToolRegistry and calls dispatch() when the LLM
emits a tool_call.  Handlers are registered with @registry.register().
"""

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Handler = Callable[..., Awaitable[str]]


class ToolRegistry:
    """
    Maps tool names → (schema, async handler).

    Handler signature: async (session, garak_state, **tool_args) -> str
      - session:     the active Session object (for file I/O, SSE emit)
      - garak_state: the GarakMissionState object (for conversation mutation)
      - **tool_args: the parsed arguments from the LLM tool call
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        self._schemas: list[dict] = []

    def register(self, schema: dict, handler: Handler) -> None:
        name = schema["function"]["name"]
        self._handlers[name] = handler
        self._schemas.append(schema)

    @property
    def schemas(self) -> list[dict]:
        """All tool schemas — passed to the LLM at each step."""
        return self._schemas

    async def dispatch(
        self,
        tool_name: str,
        tool_args: dict,
        session: Any,
        garak_state: Any,
    ) -> str:
        """
        Execute the named tool and return its string result.

        Returns an error string (not raises) so the LLM can recover.
        """
        handler = self._handlers.get(tool_name)
        if handler is None:
            return f"ERROR: unknown tool '{tool_name}'"
        try:
            return await handler(session=session, garak_state=garak_state, **tool_args)
        except Exception as exc:
            logger.exception("Tool %r raised: %s", tool_name, exc)
            return f"ERROR in {tool_name}: {exc}"


def build_registry() -> ToolRegistry:
    """
    Construct the full Phase 2 tool registry (core tools + converters).

    Handlers are closures that reference no global state; all mutable
    state flows through session + garak_state.
    """
    from arrai.tools.core_tools import (
        SEND_TO_TARGET_SCHEMA,
        BACKTRACK_SCHEMA,
        READ_VAULT_FILE_SCHEMA,
        WRITE_VAULT_ENTRY_SCHEMA,
        LOG_OBSERVATION_SCHEMA,
        ENCODE_BASE64_SCHEMA,
        ENCODE_ROT13_SCHEMA,
        ENCODE_CAESAR_SCHEMA,
        ENCODE_LEETSPEAK_SCHEMA,
        ENCODE_PIG_LATIN_SCHEMA,
        ENCODE_UNICODE_CONFUSABLES_SCHEMA,
        ENCODE_REVERSE_SCHEMA,
        ENCODE_WORD_SCRAMBLE_SCHEMA,
    )
    from arrai.tools.converters import (
        encode_base64,
        encode_rot13,
        encode_caesar,
        encode_leetspeak,
        encode_pig_latin,
        encode_unicode_confusables,
        encode_reverse,
        encode_word_scramble,
    )

    registry = ToolRegistry()

    # ── send_to_target ────────────────────────────────────────────────
    async def handle_send_to_target(session, garak_state, prompt: str, note: str = "") -> str:
        return await garak_state.send_to_target(prompt, note=note)

    registry.register(SEND_TO_TARGET_SCHEMA, handle_send_to_target)

    # ── backtrack ─────────────────────────────────────────────────────
    async def handle_backtrack(session, garak_state, turns: int, reason: str = "") -> str:
        return await garak_state.backtrack(turns=turns, reason=reason)

    registry.register(BACKTRACK_SCHEMA, handle_backtrack)

    # ── read_vault_file ───────────────────────────────────────────────
    async def handle_read_vault_file(session, garak_state, vault_path: str) -> str:
        return session.vault.read_file(vault_path)

    registry.register(READ_VAULT_FILE_SCHEMA, handle_read_vault_file)

    # ── write_vault_entry ─────────────────────────────────────────────
    async def handle_write_vault_entry(
        session,
        garak_state,
        id: str,
        title: str,
        description: str,
        example: str,
        full_content: str,
    ) -> str:
        entry = session.vault.write_entry(
            id=id,
            title=title,
            description=description,
            example=example,
            full_content=full_content,
            session_id=session.config.session_id,
        )
        return f"Vault entry '{entry.id}' saved. It will appear in your system prompt on the next mission."

    registry.register(WRITE_VAULT_ENTRY_SCHEMA, handle_write_vault_entry)

    # ── log_observation ───────────────────────────────────────────────
    async def handle_log_observation(session, garak_state, observation: str) -> str:
        session.store.append_observation(
            session_id=session.config.session_id,
            mission_id=garak_state.mission_id,
            observation=observation,
        )
        return f"Observation logged: {observation[:80]}..."

    registry.register(LOG_OBSERVATION_SCHEMA, handle_log_observation)

    # ── converters ────────────────────────────────────────────────────

    async def handle_encode_base64(session, garak_state, text: str) -> str:
        result = encode_base64(text)
        return f"Base64 encoded:\n{result}"

    registry.register(ENCODE_BASE64_SCHEMA, handle_encode_base64)

    async def handle_encode_rot13(session, garak_state, text: str) -> str:
        result = encode_rot13(text)
        return f"ROT13 encoded:\n{result}"

    registry.register(ENCODE_ROT13_SCHEMA, handle_encode_rot13)

    async def handle_encode_caesar(session, garak_state, text: str, shift: int = 3) -> str:
        result = encode_caesar(text, shift=shift)
        return f"Caesar(shift={shift}) encoded:\n{result}"

    registry.register(ENCODE_CAESAR_SCHEMA, handle_encode_caesar)

    async def handle_encode_leetspeak(session, garak_state, text: str) -> str:
        result = encode_leetspeak(text)
        return f"Leetspeak encoded:\n{result}"

    registry.register(ENCODE_LEETSPEAK_SCHEMA, handle_encode_leetspeak)

    async def handle_encode_pig_latin(session, garak_state, text: str) -> str:
        result = encode_pig_latin(text)
        return f"Pig Latin encoded:\n{result}"

    registry.register(ENCODE_PIG_LATIN_SCHEMA, handle_encode_pig_latin)

    async def handle_encode_unicode_confusables(
        session, garak_state, text: str, density: float = 0.5
    ) -> str:
        result = encode_unicode_confusables(text, density=density)
        return f"Unicode confusables (density={density}):\n{result}"

    registry.register(ENCODE_UNICODE_CONFUSABLES_SCHEMA, handle_encode_unicode_confusables)

    async def handle_encode_reverse(session, garak_state, text: str) -> str:
        result = encode_reverse(text)
        return f"Reversed:\n{result}"

    registry.register(ENCODE_REVERSE_SCHEMA, handle_encode_reverse)

    async def handle_encode_word_scramble(session, garak_state, text: str) -> str:
        result = encode_word_scramble(text)
        return f"Word-scrambled:\n{result}"

    registry.register(ENCODE_WORD_SCRAMBLE_SCHEMA, handle_encode_word_scramble)

    return registry


# Backward-compatible alias
def build_phase1_registry() -> ToolRegistry:
    """Deprecated alias for build_registry(). Use build_registry() instead."""
    return build_registry()
