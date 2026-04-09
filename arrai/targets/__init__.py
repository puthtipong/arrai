from arrai.targets.base import Target, TargetCapabilities
from arrai.targets.openai_target import OpenAITarget


def build_target(config) -> Target:
    """
    Factory: instantiate the correct Target subclass from a TargetConfig.

    Supported target_type values
    ─────────────────────────────
    openai          — OpenAI (or Azure OpenAI) chat-completions endpoint
    anthropic       — Anthropic Claude API
    azure_openai    — Azure OpenAI (alias; params must include api_base + api_version)
    custom_http     — Any HTTP REST endpoint ({prompt} substitution in body/headers)
    raw_http        — Burp-style raw HTTP request ({PROMPT} substitution)
    playwright      — Browser-based UI (CSS-selector automation via Playwright)
    guarded_agent   — Multi-stage LLM application (guardrail → router → agent)
    """
    t = config.target_type

    if t == "openai":
        return OpenAITarget(config)

    if t in ("anthropic", "azure_openai"):
        # OpenAITarget handles both; Azure needs api_base + api_version in params
        return OpenAITarget(config)

    if t == "custom_http":
        from arrai.targets.http_target import CustomHTTPTarget
        return CustomHTTPTarget(config)

    if t == "raw_http":
        from arrai.targets.raw_http_target import RawHTTPTarget
        return RawHTTPTarget(config)

    if t == "playwright":
        from arrai.targets.playwright_target import PlaywrightTarget
        return PlaywrightTarget(config)

    if t == "guarded_agent":
        from arrai.targets.guarded_agent_target import GuardedAgentTarget
        return GuardedAgentTarget(config)

    raise ValueError(
        f"Unknown target_type: {t!r}. "
        "Supported types: openai, anthropic, azure_openai, custom_http, "
        "raw_http, playwright, guarded_agent"
    )


__all__ = [
    "Target",
    "TargetCapabilities",
    "OpenAITarget",
    "build_target",
]
