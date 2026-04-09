from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TargetConfig:
    """Provider-specific target connection configuration."""

    target_type: str   # "openai" | "anthropic" | "azure_openai" | "playwright" | "custom_http"
    params: dict = field(default_factory=dict)
    # params examples:
    #   openai:       {"model": "gpt-4o", "api_key_env": "OPENAI_API_KEY", "system_prompt": "..."}
    #   anthropic:    {"model": "claude-opus-4-5", "api_key_env": "ANTHROPIC_API_KEY"}
    #   azure_openai: {"endpoint": "...", "deployment": "...", "api_key_env": "AZURE_OPENAI_KEY"}
    #   custom_http:  {"url": "...", "method": "POST", "is_stateful": false}

    def to_dict(self) -> dict:
        return {"target_type": self.target_type, "params": self.params}

    @classmethod
    def from_dict(cls, d: dict) -> "TargetConfig":
        return cls(target_type=d["target_type"], params=d.get("params", {}))


@dataclass
class SessionConfig:
    """Full configuration for one red-team session."""

    session_id: str
    target_config: TargetConfig
    objective: str

    # ── Optional seeds ────────────────────────────────────────────────
    whitebox_seed: str | None = None     # Pre-populates target.md ## Architecture
    further_context: str | None = None   # Freewrite: paths, hunches, constraints

    # ── Operational ──────────────────────────────────────────────────
    mode: Literal["autonomous", "hitl"] = "autonomous"
    max_missions: int = 20
    default_turn_budget: int = 8

    # ── Future parallelism (always 1 for now) ────────────────────────
    parallel_branches: int = 1

    # ── Model config ─────────────────────────────────────────────────
    sherlock_model: str = "gpt-5.4"
    sherlock_effort: Literal["none", "low", "medium", "high"] = "medium"
    garak_model: str = "gpt-5.4"
    garak_effort: Literal["none", "low", "medium", "high"] = "none"
    scorer_model: str = "gpt-5.4-mini"
    scorer_effort: Literal["none", "low", "medium", "high"] = "none"

    # ── Mission score threshold ───────────────────────────────────────
    # Informational hint passed to Sherlock: a scorer score at or above
    # this level means a mission was well-executed against its own criteria.
    # This does NOT trigger automatic session termination — only Sherlock
    # can declare the overall objective complete.
    success_score_threshold: float = 0.8

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        target_config: TargetConfig,
        objective: str,
        **kwargs,
    ) -> "SessionConfig":
        return cls(
            session_id=str(uuid.uuid4()),
            target_config=target_config,
            objective=objective,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "target_config": self.target_config.to_dict(),
            "objective": self.objective,
            "whitebox_seed": self.whitebox_seed,
            "further_context": self.further_context,
            "mode": self.mode,
            "max_missions": self.max_missions,
            "default_turn_budget": self.default_turn_budget,
            "parallel_branches": self.parallel_branches,
            "sherlock_model": self.sherlock_model,
            "sherlock_effort": self.sherlock_effort,
            "garak_model": self.garak_model,
            "garak_effort": self.garak_effort,
            "scorer_model": self.scorer_model,
            "scorer_effort": self.scorer_effort,
            "success_score_threshold": self.success_score_threshold,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SessionConfig":
        # Auto-generate session_id if missing or still the example placeholder
        sid = d.get("session_id", "")
        if not sid or "replace-with" in sid:
            sid = str(uuid.uuid4())
        return cls(
            session_id=sid,
            target_config=TargetConfig.from_dict(d["target_config"]),
            objective=d["objective"],
            whitebox_seed=d.get("whitebox_seed"),
            further_context=d.get("further_context"),
            mode=d.get("mode", "autonomous"),
            max_missions=d.get("max_missions", 20),
            default_turn_budget=d.get("default_turn_budget", 8),
            parallel_branches=d.get("parallel_branches", 1),
            sherlock_model=d.get("sherlock_model", "gpt-5.4"),
            sherlock_effort=d.get("sherlock_effort", "medium"),
            garak_model=d.get("garak_model", "gpt-5.4"),
            garak_effort=d.get("garak_effort", "none"),
            scorer_model=d.get("scorer_model", "gpt-5.4-mini"),
            scorer_effort=d.get("scorer_effort", "none"),
            success_score_threshold=d.get("success_score_threshold", 0.8),
        )
