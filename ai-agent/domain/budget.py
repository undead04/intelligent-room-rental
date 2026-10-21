"""Nghiệp vụ ngân sách: MỘT nơi duy nhất cho công thức nới ngân sách và so sánh với giá thị trường.

Trước đây logic này nằm ở 3 nơi (tool search_rooms, grounding, graph) và có các lỗi:
  - Khi backend không có số liệu thì TỰ BỊA giá sàn (2.000.000 / 3.200.000 / user_max * 1.3) rồi nói với người dùng như thật.
  - Mặc định city_id = 79 (TP.HCM) cho mọi người dùng không rõ thành phố.
  - Giá sàn lấy từ `minimum_price` của vài tin đăng dị thường.
Quy tắc mới: KHÔNG có số liệu thì KHÔNG khẳng định gì về thị trường (chỉ đề xuất nới nhẹ); không mặc định thành phố;
chỉ kết luận "ngân sách thấp hơn mặt bằng" khi mẫu đủ lớn.

Module này THUẦN: không import tools/HTTP. Nguồn dữ liệu được truyền vào dưới dạng `fetcher`.
"""

from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from domain.enums import RoomType

RELAX_FACTOR = 1.15            # nới ngân sách +15%
TIGHTEN_FACTOR = 0.85          # hạ ngân sách -15%
GAP_RATIO = 0.85               # ngân sách < 85% giá sàn => "thấp hơn mặt bằng"
MIN_SAMPLE = 20                # ít hơn ngần này tin đăng thì không tin giá sàn
DORM_THRESHOLD = 2_000_000.0   # ngân sách <= mức này thì gợi ý ký túc xá/sleepbox
ROUND_STEP = 50_000.0          # làm tròn LÊN để số tiền đề xuất gọn (3.45 chứ không phải 3.4501 triệu)

# Mặc định thành phố là LỰA CHỌN CÓ CHỦ ĐÍCH của vận hành (vd HOMIGO_DEFAULT_CITY_ID=79), không phải thói quen ngầm.
_env_city = os.environ.get("HOMIGO_DEFAULT_CITY_ID", "").strip()
DEFAULT_CITY_ID: Optional[int] = int(_env_city) if _env_city.isdigit() else None


def round_up_step(v: float, step: float = ROUND_STEP) -> float:
    return float(math.ceil(v / step) * step)


def relax_budget(user_max: float) -> float:
    """Ngân sách sau khi nới nhẹ (+15%, làm tròn lên 50k)."""
    return round_up_step(float(user_max) * RELAX_FACTOR)


def tighten_budget(user_max: float) -> float:
    """Ngân sách sau khi hạ xuống (-15%, làm tròn 50k)."""
    return round_up_step(float(user_max) * TIGHTEN_FACTOR)


# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MarketStats:
    min_price: float
    avg_price: Optional[float] = None
    total_listings: Optional[int] = None

    @classmethod
    def from_backend(cls, general: Optional[dict[str, Any]]) -> Optional["MarketStats"]:
        """Từ `price_stats_general` của /listings/price-stats. Thiếu/không hợp lệ -> None (không đoán)."""
        if not isinstance(general, dict):
            return None
        try:
            mn = float(general.get("minimum_price_vnd") or 0)
        except (TypeError, ValueError):
            return None
        if mn <= 0:
            return None

        def _f(key: str) -> Optional[float]:
            try:
                v = float(general.get(key) or 0)
                return v if v > 0 else None
            except (TypeError, ValueError):
                return None

        total = general.get("total_listings")
        return cls(min_price=mn, avg_price=_f("average_price_vnd"), total_listings=int(total) if isinstance(total, (int, float)) else None)

    @property
    def reliable(self) -> bool:
        """Mẫu đủ lớn để tin giá sàn. Backend không báo số lượng thì không có căn cứ bác bỏ nên vẫn coi là dùng được."""
        return self.total_listings is None or self.total_listings >= MIN_SAMPLE


@dataclass(frozen=True)
class BudgetProposal:
    user_budget: float
    proposed_budget: float
    is_market_gap: bool
    suggest_dormitory: bool
    market: Optional[MarketStats] = None
    area_name: Optional[str] = None

    @property
    def has_market_data(self) -> bool:
        return self.market is not None


def propose_budget(
    user_max: Optional[float],
    market: Optional[MarketStats] = None,
    *,
    area_name: Optional[str] = None,
    excluded_room_types: Iterable[RoomType] = (),
) -> Optional[BudgetProposal]:
    """Đề xuất ngân sách. None nếu người dùng chưa đặt ngân sách tối đa."""
    if not user_max or user_max <= 0:
        return None
    user_max = float(user_max)
    is_gap = bool(market and market.reliable and user_max < market.min_price * GAP_RATIO)
    proposed = round_up_step(market.min_price) if is_gap and market else relax_budget(user_max)
    dorm = user_max <= DORM_THRESHOLD and RoomType.SLEEPBOX not in set(excluded_room_types or ())
    return BudgetProposal(user_budget=user_max, proposed_budget=proposed, is_market_gap=is_gap,
                          suggest_dormitory=dorm, market=market, area_name=area_name)


# ---------------------------------------------------------------------------
# Cache TTL (thread-safe; cache cả kết quả "không có" để backend sập không bị gọi lại mỗi lượt)
# ---------------------------------------------------------------------------
class TTLCache:
    def __init__(self, ttl: float = 600.0, miss_ttl: float = 60.0, maxsize: int = 500, clock: Callable[[], float] = time.monotonic):
        self.ttl, self.miss_ttl, self.maxsize, self._clock = ttl, miss_ttl, maxsize, clock
        self._data: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> tuple[bool, Any]:
        with self._lock:
            hit = self._data.get(key)
            if hit and hit[0] > self._clock():
                return True, hit[1]
            self._data.pop(key, None)
            return False, None

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            if len(self._data) >= self.maxsize:
                self._data.pop(min(self._data, key=lambda k: self._data[k][0]), None)
            self._data[key] = (self._clock() + (self.ttl if value is not None else self.miss_ttl), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


_MARKET_CACHE = TTLCache()
MarketFetcher = Callable[..., Optional[dict[str, Any]]]


def fetch_market_stats(
    fetcher: Optional[MarketFetcher],
    *,
    city_id: Optional[int],
    district_id: Optional[int] = None,
    room_type_id: Optional[int] = None,
    cache: TTLCache = _MARKET_CACHE,
) -> Optional[MarketStats]:
    """Lấy thống kê giá. KHÔNG có city_id (kể cả DEFAULT_CITY_ID) -> trả None, không đoán thành phố.

    `fetcher(city_id=, district_id=, room_type_id=)` trả dict `price_stats_general` hoặc None; lỗi mạng nên trả None.
    """
    city = city_id if city_id is not None else DEFAULT_CITY_ID
    if fetcher is None or city is None:
        return None
    key = (city, district_id, room_type_id)
    hit, val = cache.get(key)
    if hit:
        return val
    try:
        stats = MarketStats.from_backend(fetcher(city_id=city, district_id=district_id, room_type_id=room_type_id))
    except Exception:
        stats = None
    cache.set(key, stats)
    return stats
