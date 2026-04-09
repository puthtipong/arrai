from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arrai.models.message import Message


@dataclass
class Auftrag:
    """
    Sherlock's orders to Garak.

    Auftragstaktik style: specify *what* must be achieved and *why* (situation),
    leave Garak freedom of action on *how*.
    """

    mission_id: str
    session_id: str
    issued_at: datetime

    # ── Task ──────────────────────────────────────────────────────────
    objective: str           # What Garak must achieve this mission
    success_criteria: str    # Explicit, evaluable condition for success
    turn_budget: int         # Max send_to_target calls Garak may make

    # ── Situation ─────────────────────────────────────────────────────
    situation: str                        # Sherlock's read of current state
    suggested_angles: list[str] = field(default_factory=list)  # Hints (not mandatory)
    avoid: list[str] = field(default_factory=list)              # Confirmed dead ends

    # ── Conversation context ──────────────────────────────────────────
    # Non-empty when Sherlock wants Garak to branch from a prior turn.
    conversation_history: list = field(default_factory=list)   # list[Message]

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        session_id: str,
        objective: str,
        success_criteria: str,
        turn_budget: int,
        situation: str,
        suggested_angles: list[str] | None = None,
        avoid: list[str] | None = None,
        conversation_history: list | None = None,
    ) -> "Auftrag":
        return cls(
            mission_id=str(uuid.uuid4()),
            session_id=session_id,
            issued_at=datetime.now(timezone.utc),
            objective=objective,
            success_criteria=success_criteria,
            turn_budget=turn_budget,
            situation=situation,
            suggested_angles=suggested_angles or [],
            avoid=avoid or [],
            conversation_history=conversation_history or [],
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "mission_id": self.mission_id,
            "session_id": self.session_id,
            "issued_at": self.issued_at.isoformat(),
            "objective": self.objective,
            "success_criteria": self.success_criteria,
            "turn_budget": self.turn_budget,
            "situation": self.situation,
            "suggested_angles": self.suggested_angles,
            "avoid": self.avoid,
            "conversation_history": [
                m.to_dict() if hasattr(m, "to_dict") else m
                for m in self.conversation_history
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Auftrag":
        from arrai.models.message import Message

        return cls(
            mission_id=d["mission_id"],
            session_id=d["session_id"],
            issued_at=datetime.fromisoformat(d["issued_at"]),
            objective=d["objective"],
            success_criteria=d["success_criteria"],
            turn_budget=d["turn_budget"],
            situation=d["situation"],
            suggested_angles=d.get("suggested_angles", []),
            avoid=d.get("avoid", []),
            conversation_history=[
                Message.from_dict(m) for m in d.get("conversation_history", [])
            ],
        )

    def render_for_garak(self) -> str:
        """Human-readable Auftrag block injected into Garak's context."""
        lines = [
            "═" * 60,
            "AUFTRAG (MISSION ORDERS)",
            "═" * 60,
            f"Mission ID  : {self.mission_id}",
            f"Turn Budget : {self.turn_budget}",
            "",
            "OBJECTIVE",
            "─" * 40,
            self.objective,
            "",
            "SUCCESS CRITERIA",
            "─" * 40,
            self.success_criteria,
            "",
            "SITUATION",
            "─" * 40,
            self.situation,
        ]
        if self.suggested_angles:
            lines += ["", "SUGGESTED ANGLES (not mandatory):", "─" * 40]
            lines += [f"  • {a}" for a in self.suggested_angles]
        if self.avoid:
            lines += ["", "AVOID — CONFIRMED DEAD ENDS:", "─" * 40]
            lines += [f"  ✗ {a}" for a in self.avoid]
        lines.append("═" * 60)
        return "\n".join(lines)
