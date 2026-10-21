import pytest

from domain.budget import (
    GAP_RATIO, MIN_SAMPLE, MarketStats, TTLCache, fetch_market_stats, propose_budget, relax_budget, round_up_step,
    tighten_budget,
)
from domain.enums import RoomType


def test_rounding_and_relax():
    assert round_up_step(3_450_001) == 3_500_000 and round_up_step(3_450_000) == 3_450_000
    assert relax_budget(3_000_000) == 3_450_000
    assert relax_budget(3_500_000) == 4_050_000
    assert relax_budget(1_000_000) == 1_150_000
    assert tighten_budget(4_000_000) == 3_400_000
    assert tighten_budget(3_000_000) == 2_550_000


def test_market_stats_from_backend():
    s = MarketStats.from_backend({"minimum_price_vnd": 2_000_000, "average_price_vnd": 3_200_000, "total_listings": 120})
    assert (s.min_price, s.avg_price, s.total_listings) == (2_000_000, 3_200_000, 120) and s.reliable
    for bad in (None, {}, {"minimum_price_vnd": 0}, {"minimum_price_vnd": "abc"}, "x", []):
        assert MarketStats.from_backend(bad) is None
    assert not MarketStats.from_backend({"minimum_price_vnd": 1_000_000, "total_listings": MIN_SAMPLE - 1}).reliable
    assert MarketStats.from_backend({"minimum_price_vnd": 1_000_000}).reliable          # không báo số lượng -> không bác bỏ


@pytest.mark.parametrize("user_max", [None, 0, -5])
def test_no_budget_no_proposal(user_max):
    assert propose_budget(user_max) is None


def test_no_market_data_never_claims_gap_and_invents_nothing():
    bp = propose_budget(1_200_000, None, area_name="Q1")             # bản cũ bịa giá sàn 2tr/3.2tr ở đây
    assert not bp.is_market_gap and not bp.has_market_data and bp.market is None
    assert bp.proposed_budget == relax_budget(1_200_000)


def test_market_gap_uses_market_floor():
    m = MarketStats(min_price=2_000_000, avg_price=3_000_000, total_listings=100)
    bp = propose_budget(1_500_000, m)
    assert bp.is_market_gap and bp.proposed_budget == 2_000_000 and bp.proposed_budget > bp.user_budget
    boundary = propose_budget(2_000_000 * GAP_RATIO, m)               # đúng ngưỡng -> chưa coi là gap
    assert not boundary.is_market_gap
    assert not propose_budget(2_500_000, m).is_market_gap


def test_unreliable_sample_blocks_gap_claim():
    m = MarketStats(min_price=2_000_000, total_listings=3)            # giá sàn từ 3 tin đăng dị thường
    bp = propose_budget(1_000_000, m)
    assert not bp.is_market_gap and bp.proposed_budget == relax_budget(1_000_000)


def test_dormitory_suggestion_rules():
    assert propose_budget(1_800_000).suggest_dormitory
    assert not propose_budget(2_500_000).suggest_dormitory
    assert not propose_budget(1_800_000, excluded_room_types=[RoomType.SLEEPBOX]).suggest_dormitory   # đã loại trừ thì không gợi ý
    assert propose_budget(1_800_000, excluded_room_types=[RoomType.STUDIO]).suggest_dormitory


# ---------------- cache + fetch ----------------
class Clock:
    t = 0.0
    def __call__(self): return self.t


def test_ttl_cache_expiry_and_negative_caching():
    clk = Clock()
    c = TTLCache(ttl=100, miss_ttl=10, clock=clk)
    c.set("a", 1); c.set("none", None)
    assert c.get("a") == (True, 1) and c.get("none") == (True, None)
    clk.t = 11
    assert c.get("none") == (False, None) and c.get("a") == (True, 1)      # lỗi hết hạn sớm hơn
    clk.t = 101
    assert c.get("a") == (False, None)


def test_ttl_cache_maxsize_evicts_oldest():
    clk = Clock()
    c = TTLCache(ttl=100, maxsize=2, clock=clk)
    c.set(1, "a"); clk.t = 1; c.set(2, "b"); clk.t = 2; c.set(3, "c")
    assert c.get(1) == (False, None) and c.get(2)[0] and c.get(3)[0]


def test_fetch_never_guesses_city_and_caches():
    calls = []
    def fetcher(**kw):
        calls.append(kw)
        return {"minimum_price_vnd": 2_000_000, "total_listings": 50}
    cache = TTLCache()
    assert fetch_market_stats(fetcher, city_id=None, cache=cache) is None and calls == []   # không có city -> không gọi, không đoán 79
    assert fetch_market_stats(None, city_id=79, cache=cache) is None
    a = fetch_market_stats(fetcher, city_id=79, district_id=5, room_type_id=1, cache=cache)
    b = fetch_market_stats(fetcher, city_id=79, district_id=5, room_type_id=1, cache=cache)
    assert a is b and a.min_price == 2_000_000 and len(calls) == 1
    assert calls[0] == {"city_id": 79, "district_id": 5, "room_type_id": 1}


def test_fetch_error_is_cached_as_miss():
    calls = []
    def boom(**kw):
        calls.append(1); raise RuntimeError("backend down")
    cache = TTLCache()
    assert fetch_market_stats(boom, city_id=79, cache=cache) is None
    assert fetch_market_stats(boom, city_id=79, cache=cache) is None
    assert len(calls) == 1                                               # không gọi lại mỗi lượt khi backend sập


def test_default_city_is_explicit_config(monkeypatch):
    import domain.budget as b
    monkeypatch.setattr(b, "DEFAULT_CITY_ID", 79)
    calls = []
    out = b.fetch_market_stats(lambda **kw: calls.append(kw) or {"minimum_price_vnd": 1_500_000}, city_id=None, cache=TTLCache())
    assert out.min_price == 1_500_000 and calls[0]["city_id"] == 79
