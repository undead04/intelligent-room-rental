"""Domain models, schemas, enums, và value objects cho Homigo AI Agent."""

from domain.budget import (
    DORM_THRESHOLD,
    GAP_RATIO,
    MIN_SAMPLE,
    RELAX_FACTOR,
    ROUND_STEP,
    TIGHTEN_FACTOR,
    BudgetProposal,
    MarketStats,
    fetch_market_stats,
    propose_budget,
    relax_budget,
    round_up_step,
    tighten_budget,
)
from domain.enums import (
    Amenity,
    HitlAction,
    RoomType,
)
from domain.filters import (
    drop_excluded_room_types,
    renumber,
)
from domain.schemas import (
    AgentResponse,
    DecisionInsight,
    GroundingReport,
    HitlOption,
    HitlProposal,
    RoomItem,
    TradeOffAnalysis,
    UserPreferenceState,
    format_vnd_million,
    rank_text,
)

__all__ = [
    # schemas
    "RoomItem",
    "TradeOffAnalysis",
    "DecisionInsight",
    "UserPreferenceState",
    "HitlOption",
    "HitlProposal",
    "GroundingReport",
    "AgentResponse",
    "format_vnd_million",
    "rank_text",
    # enums
    "Amenity",
    "RoomType",
    "HitlAction",
    # budget
    "RELAX_FACTOR",
    "TIGHTEN_FACTOR",
    "GAP_RATIO",
    "MIN_SAMPLE",
    "DORM_THRESHOLD",
    "ROUND_STEP",
    "round_up_step",
    "relax_budget",
    "tighten_budget",
    "MarketStats",
    "BudgetProposal",
    "propose_budget",
    "fetch_market_stats",
    # filters
    "renumber",
    "drop_excluded_room_types",
]
