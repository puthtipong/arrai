from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal


@dataclass
class Message:
    """A single turn in a conversation."""

    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def to_api_dict(self) -> dict:
        """Minimal dict for LLM API calls (role + content only)."""
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        ts = d.get("timestamp")
        return cls(
            role=d["role"],
            content=d["content"],
            timestamp=datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc),
            metadata=d.get("metadata", {}),
        )
