"""Module Trí tuệ (Intelligence): NLU, Dynamic MCDM Intent Weights, Decision Insights & Advice."""

from intelligence.decision import (
    ADVICE_RULES,
    DEFAULT_CHECKLIST,
    FACTOR_VN,
    MAX_FIELD_CHARS,
    Advice,
    build_decision_insights,
    fmt_money_short,
    generate_advice,
    price_trade_off,
    render_advice,
    room_lines,
)
from intelligence.intent_weights import (
    CRITERIA,
    DEFAULT_BASE_WEIGHTS,
    compute_normalized_weights,
)
from intelligence.nlu import (
    PreferencePatch,
    Priorities,
    TurnAnalysis,
    analyze_turn,
    apply_patch,
    apply_priorities,
    build_nlu_system_prompt,
    mult_to_level,
    multipliers_to_levels,
    sanitize_user_text,
)
from intelligence.payload_builder import (
    build_decision_context_message,
    build_decision_query_message,
    build_decision_user_message,
    compact_room,
    format_retry_feedback,
)
from intelligence.understand import (
    interpret_turn,
    route_after_understand,
)

__all__ = [
    # NLU
    "Priorities",
    "PreferencePatch",
    "TurnAnalysis",
    "apply_patch",
    "apply_priorities",
    "multipliers_to_levels",
    "mult_to_level",
    "build_nlu_system_prompt",
    "sanitize_user_text",
    "analyze_turn",
    # Understand
    "interpret_turn",
    "route_after_understand",
    # Dynamic MCDM
    "CRITERIA",
    "DEFAULT_BASE_WEIGHTS",
    "compute_normalized_weights",
    # Payload builder
    "compact_room",
    "format_retry_feedback",
    "build_decision_user_message",
    "build_decision_context_message",
    "build_decision_query_message",
    # Decision
    "FACTOR_VN",
    "DEFAULT_CHECKLIST",
    "fmt_money_short",
    "price_trade_off",
    "room_lines",
    "build_decision_insights",
    "MAX_FIELD_CHARS",
    "Advice",
    "ADVICE_RULES",
    "render_advice",
    "generate_advice",
]
