from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from arrai.models.message import Message


# Terminal conditions Garak can report
TerminalCondition = Literal["success", "dead_end", "discovery", "budget_exhausted"]


@dataclass
class ConversationTrace:
    """Complete ordered message sequence for one mission."""

    mission_id: str
    target_id: str
    messages: list = field(default_factory=list)  # list[Message]

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "target_id": self.target_id,
            "messages": [
                m.to_dict() if hasattr(m, "to_dict") else m for m in self.messages
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConversationTrace":
        from arrai.models.message import Message

        return cls(
            mission_id=d["mission_id"],
            target_id=d["target_id"],
            messages=[Message.from_dict(m) for m in d.get("messages", [])],
        )


@dataclass
class MissionReport:
    """
    Garak's full report to Sherlock at mission end.

    Contains the raw trace (for Sherlock's full-fidelity observation),
    Garak's self-assessment, and the independent scorer result.
    """

    mission_id: str
    session_id: str
    terminal_condition: TerminalCondition

    # ── Raw record ────────────────────────────────────────────────────
    conversation_trace: ConversationTrace

    # ── Garak self-assessment ─────────────────────────────────────────
    garak_score: float          # 0.0–1.0 against success_criteria
    garak_insights: str         # Tactical observations / what was noticed
    techniques_used: list[str]  # IDs of techniques / tools applied

    # ── Independent scorer (filled by session runner after mission) ───
    scorer_score: float = 0.0
    scorer_rationale: str = ""

    # ── Discovery payload ─────────────────────────────────────────────
    # Only meaningful when terminal_condition == "discovery"
    discovery: str | None = None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "session_id": self.session_id,
            "terminal_condition": self.terminal_condition,
            "conversation_trace": self.conversation_trace.to_dict(),
            "garak_score": self.garak_score,
            "garak_insights": self.garak_insights,
            "techniques_used": self.techniques_used,
            "scorer_score": self.scorer_score,
            "scorer_rationale": self.scorer_rationale,
            "discovery": self.discovery,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MissionReport":
        return cls(
            mission_id=d["mission_id"],
            session_id=d["session_id"],
            terminal_condition=d["terminal_condition"],
            conversation_trace=ConversationTrace.from_dict(d["conversation_trace"]),
            garak_score=d["garak_score"],
            garak_insights=d["garak_insights"],
            techniques_used=d.get("techniques_used", []),
            scorer_score=d.get("scorer_score", 0.0),
            scorer_rationale=d.get("scorer_rationale", ""),
            discovery=d.get("discovery"),
        )

    def summary_line(self) -> str:
        """One-line summary for Garak's adaptive context."""
        return (
            f"[{self.mission_id[:8]}] "
            f"{self.terminal_condition.upper()} | "
            f"garak={self.garak_score:.2f} scorer={self.scorer_score:.2f} | "
            f"techniques={self.techniques_used} | "
            f"{self.garak_insights[:120]}"
        )
