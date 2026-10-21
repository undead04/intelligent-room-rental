"""Decision intelligence: Phân tích quyết định, trade-offs, checklist và render advice."""

from intelligence.advice import (
    ADVICE_RULES,
    MAX_FIELD_CHARS,
    Advice,
    generate_advice,
    render_advice,
)
from intelligence.insights import (
    DEFAULT_CHECKLIST,
    FACTOR_VN,
    build_decision_insights,
    fmt_money_short,
    price_trade_off,
    room_lines,
)

__all__ = [
    # insights
    "FACTOR_VN",
    "DEFAULT_CHECKLIST",
    "fmt_money_short",
    "price_trade_off",
    "room_lines",
    "build_decision_insights",
    # advice
    "MAX_FIELD_CHARS",
    "Advice",
    "ADVICE_RULES",
    "render_advice",
    "generate_advice",
]
