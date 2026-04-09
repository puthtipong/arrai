from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arrai.models.auftrag import Auftrag


@dataclass
class OODARecord:
    """
    Sherlock's reasoning output for one OODA cycle.

    The Orient and Decide sections (not Observe) are fed back into
    Sherlock's context on subsequent cycles as a compact reasoning chain.
    """

    cycle_id: str
    session_id: str
    timestamp: datetime
    mission_id_reviewed: str | None  # Which MissionReport triggered this cycle

    # ── OODA sections ─────────────────────────────────────────────────
    observe: str   # What Sherlock gathered and noticed
    orient: str    # Analysis, updated mental model
    decide: str    # Decision + rationale
    auftrag: "Auftrag | None"  # The resulting orders (None if action=complete)

    # ── Action metadata ───────────────────────────────────────────────
    action_type: str  # "mission" | "session_reset" | "complete" | "pause_for_hitl"
    update_target_md: str | None = None  # New target.md content (if changed)
    update_plan_md: str | None = None    # New plan.md content (if changed)

    # ── Completion report (only when action_type == "complete") ───────
    session_summary: str | None = None
    # Sherlock's narrative: what worked, what failed, winning technique chain,
    # target weaknesses, and recommendations for follow-up.

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        session_id: str,
        mission_id_reviewed: str | None,
        observe: str,
        orient: str,
        decide: str,
        action_type: str,
        auftrag: "Auftrag | None" = None,
        update_target_md: str | None = None,
        update_plan_md: str | None = None,
        session_summary: str | None = None,
    ) -> "OODARecord":
        return cls(
            cycle_id=str(uuid.uuid4()),
            session_id=session_id,
            timestamp=datetime.now(timezone.utc),
            mission_id_reviewed=mission_id_reviewed,
            observe=observe,
            orient=orient,
            decide=decide,
            auftrag=auftrag,
            action_type=action_type,
            update_target_md=update_target_md,
            update_plan_md=update_plan_md,
            session_summary=session_summary,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "mission_id_reviewed": self.mission_id_reviewed,
            "observe": self.observe,
            "orient": self.orient,
            "decide": self.decide,
            "action_type": self.action_type,
            "auftrag": self.auftrag.to_dict() if self.auftrag else None,
            "update_target_md": self.update_target_md,
            "update_plan_md": self.update_plan_md,
            "session_summary": self.session_summary,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OODARecord":
        from arrai.models.auftrag import Auftrag

        return cls(
            cycle_id=d["cycle_id"],
            session_id=d["session_id"],
            timestamp=datetime.fromisoformat(d["timestamp"]),
            mission_id_reviewed=d.get("mission_id_reviewed"),
            observe=d["observe"],
            orient=d["orient"],
            decide=d["decide"],
            action_type=d["action_type"],
            auftrag=Auftrag.from_dict(d["auftrag"]) if d.get("auftrag") else None,
            update_target_md=d.get("update_target_md"),
            update_plan_md=d.get("update_plan_md"),
            session_summary=d.get("session_summary"),
        )

    def reasoning_chain_entry(self) -> str:
        """
        Compact repr fed back to Sherlock as his reasoning chain.
        Orient + Decide only — Observe is redundant with the raw traces.
        """
        return (
            f"── Cycle {self.cycle_id[:8]} "
            f"(reviewed mission: {self.mission_id_reviewed or 'none'}) ──\n"
            f"ORIENT:\n{self.orient}\n\n"
            f"DECIDE:\n{self.decide}\n"
            f"Action: {self.action_type}\n"
        )
