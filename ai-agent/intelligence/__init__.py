"""Module Trí tuệ (Intelligence): NLU, NLU Fallback, Dynamic MCDM Intent Weights, Decision Insights & Advice."""

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
    detect_intent_multipliers,
)
from intelligence.nlu import (
    PreferencePatch,
    Priorities,
    TurnAnalysis,
    analyze_turn,
    apply_patch,
    apply_priorities,
    build_system_prompt,
    mult_to_level,
    multipliers_to_levels,
    sanitize_user_text,
)
from intelligence.nlu_fallback import (
    detect_hitl_action,
    detect_room_followup,
    detect_vague_location,
    legacy_analysis,
)
from intelligence.payload_builder import (
    build_decision_user_message,
    compact_room,
    format_retry_feedback,
)
from intelligence.understand import (
    CUSTOM_TEXT,
    KEEP_TEXT,
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
    "build_system_prompt",
    "sanitize_user_text",
    "analyze_turn",
    # NLU Fallback
    "detect_hitl_action",
    "detect_room_followup",
    "detect_vague_location",
    "legacy_analysis",
    # Understand
    "CUSTOM_TEXT",
    "KEEP_TEXT",
    "interpret_turn",
    "route_after_understand",
    # Dynamic MCDM
    "CRITERIA",
    "DEFAULT_BASE_WEIGHTS",
    "detect_intent_multipliers",
    "compute_normalized_weights",
    # Payload builder
    "compact_room",
    "format_retry_feedback",
    "build_decision_user_message",
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
