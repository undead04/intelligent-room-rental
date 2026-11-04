"""Domain models, schemas, enums, và value objects cho Homigo AI Agent."""

from domain.budget import (
    DORM_THRESHOLD,
    GAP_RATIO,
    MIN_SAMPLE,
    ROUND_STEP,
    BudgetProposal,
    MarketStats,
    fetch_market_stats,
    propose_budget,
    round_up_step,
)
from domain.enums import (
    Amenity,
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
    MarketContext,
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
    "MarketContext",
    "GroundingReport",
    "AgentResponse",
    "format_vnd_million",
    "rank_text",
    # enums
    "Amenity",
    "RoomType",
    # budget
    "GAP_RATIO",
    "MIN_SAMPLE",
    "DORM_THRESHOLD",
    "ROUND_STEP",
    "round_up_step",
    "MarketStats",
    "BudgetProposal",
    "propose_budget",
    "fetch_market_stats",
    # filters
    "renumber",
    "drop_excluded_room_types",
]
