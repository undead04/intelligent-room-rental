"""Sinh dữ liệu TỔNG HỢP cho kiểm chứng câu trả lời: câu sạch (nhiều cách viết số tiền/diện tích) và câu bị tiêm MỘT lỗi.
Tất định theo seed. Lưu ý: đây là đo bộ kiểm tra trên lỗi do ta chủ động tiêm, KHÔNG phải tỉ lệ ảo giác của LLM."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from domain.schemas import RoomItem, UserPreferenceState


def fmt_triệu(v: float) -> str:
    return f"{v / 1e6:.2f}".rstrip("0").rstrip(".") + " triệu"


def fmt_tr(v: float) -> str:                       # 2tr85
    m = v / 1e6
    whole, frac = int(m), round(m - int(m), 2)
    return f"{whole}tr" + (f"{round(frac * 100):02d}".rstrip("0") if frac else "")


def fmt_dot_d(v: float) -> str:                    # 2.850.000đ
    return f"{int(v):,}".replace(",", ".") + "đ"


def fmt_k(v: float) -> str:                        # 2850k
    return f"{int(round(v / 1000))}k"


PRICE_FORMATS: dict[str, Callable[[float], str]] = {"triệu": fmt_triệu, "tr": fmt_tr, "dot_d": fmt_dot_d, "k": fmt_k}


def fmt_dist(meters: int, style: str) -> str:
    return f"{meters}m" if style == "m" else f"{meters / 1000:g} km"


DISTANCES = [120, 250, 450, 800, 1200, 2500, 4000]


@dataclass
class GroundingCase:
    label: str                    # "clean" | "hallucinated"
    mutation: Optional[str]       # None cho câu sạch
    rooms: list[RoomItem]
    pref: UserPreferenceState
    answer: str
    evidence: list[str] = field(default_factory=list)
    clean_kind: str = "plain"     # plain | with_tool


def _rooms(rng: random.Random) -> list[RoomItem]:
    n = rng.randint(2, 4)
    prices = rng.sample(range(30, 121), n)                                  # 1.5M .. 6M, bước 50k
    areas = rng.sample(range(12, 46), n)
    dists = rng.sample(DISTANCES, n)
    out = []
    for i, (p, a, d) in enumerate(zip(prices, areas, dists), 1):
        pr = p * 50_000.0
        out.append(RoomItem(id=f"nhatot_{rng.randint(10**8, 10**9 - 1)}", rank=i, title=f"Phòng trọ số {i}", price=f"{pr / 1e6:g} triệu/tháng",
                            priceNum=pr, area_m2=float(a), address=f"{rng.randint(1, 99)} Đường Lê Lợi", distance=fmt_dist(d, "m" if d < 1000 else "km")))
    return out


def _answer(rng: random.Random, rooms: list[RoomItem], price_fmt: str, area_fmt: str, tool_deposit: Optional[int],
            price_override: Optional[dict[int, float]] = None, area_override: Optional[dict[int, float]] = None,
            dist_override: Optional[dict[int, str]] = None) -> str:
    """Dựng câu trả lời từ dữ liệu; lỗi được tiêm bằng tham số ghi đè (KHÔNG thay chuỗi, tránh sinh văn bản rác kiểu '3.26.95 triệu')."""
    pf = PRICE_FORMATS[price_fmt]
    lines = ["Mình gợi ý các phòng sau:"]
    for i, r in enumerate(rooms[:3]):
        price = (price_override or {}).get(i, r.priceNum)
        area = int((area_override or {}).get(i, r.area_m2))
        a = f"{area} m²" if area_fmt == "m²" else f"{area}m2"
        dist = (dist_override or {}).get(i, r.distance)
        lines.append(f"- {r.title}: giá {pf(price)}, rộng {a}, cách điểm bạn chọn {dist}.")
    if len(rooms) > 1:
        d = abs(rooms[0].priceNum - rooms[1].priceNum)
        if d >= 10_000:
            lines.append(f"Top 1 chênh Top 2 khoảng {PRICE_FORMATS[price_fmt](d)} mỗi tháng.")
    if tool_deposit:
        lines.append(f"Theo thông tin chi tiết, tiền cọc {fmt_triệu(tool_deposit)}.")
    return "\n".join(lines)


def _far(rng: random.Random, refs: list[float], lo: int, hi: int, step: int, gap: float) -> float:
    while True:
        v = rng.randrange(lo, hi, step)
        if all(abs(v - r) > gap for r in refs):
            return float(v)


def generate(seed: int = 7, n_clean: int = 120, n_per_mutation: int = 60) -> list[GroundingCase]:
    rng = random.Random(seed)
    cases: list[GroundingCase] = []

    def base(price_fmt: Optional[str] = None, with_tool: bool = False):
        rooms = _rooms(rng)
        pref = UserPreferenceState(max_price=max(r.priceNum for r in rooms) + 500_000)
        pf = price_fmt or rng.choice(list(PRICE_FORMATS))
        af = rng.choice(["m²", "m2"])
        deposit = rng.choice([2_000_000, 3_000_000, 4_000_000]) if with_tool else None
        ev = [json.dumps({"ok": True, "data": {"deposit": deposit}})] if with_tool else []
        return rooms, pref, pf, af, deposit, ev

    for i in range(n_clean):
        with_tool = i % 4 == 0
        rooms, pref, pf, af, dep, ev = base(with_tool=with_tool)
        cases.append(GroundingCase("clean", None, rooms, pref, _answer(rng, rooms, pf, af, dep), ev, "with_tool" if with_tool else "plain"))

    def refs_of(rooms: list[RoomItem], pref: UserPreferenceState) -> list[float]:
        pr = [r.priceNum for r in rooms]
        return pr + [abs(a - b) for i, a in enumerate(pr) for b in pr[i + 1:]] + [pref.max_price or 0]

    for fmt in PRICE_FORMATS:                                                # giá sai, theo từng cách viết
        for _ in range(n_per_mutation):
            rooms, pref, pf, af, dep, ev = base(price_fmt=fmt)
            wrong = _far(rng, refs_of(rooms, pref), 1_000_000, 8_000_000, 50_000, 400_000)
            ans = _answer(rng, rooms, pf, af, dep, price_override={rng.randrange(min(3, len(rooms))): wrong})
            cases.append(GroundingCase("hallucinated", f"price_wrong/{fmt}", rooms, pref, ans, ev))

    for _ in range(n_per_mutation):                                          # diện tích sai
        rooms, pref, pf, af, dep, ev = base()
        areas = [r.area_m2 for r in rooms]
        diffs = [abs(a - b) for i, a in enumerate(areas) for b in areas[i + 1:]]
        wrong = _far(rng, areas + diffs, 10, 80, 1, 3.0)
        cases.append(GroundingCase("hallucinated", "area_wrong", rooms, pref, _answer(rng, rooms, pf, af, dep, area_override={0: wrong}), ev))

    for _ in range(n_per_mutation):                                          # khoảng cách sai: khác MỌI khoảng cách có trong dữ liệu
        rooms, pref, pf, af, dep, ev = base()
        known = [m for m in DISTANCES if fmt_dist(m, "m" if m < 1000 else "km") in {r.distance for r in rooms}]
        far = [d for d in DISTANCES if all(abs(d - k) > max(60.0, 0.4 * k, 0.4 * d) for k in known)]
        wrong = rng.choice(far)
        shown = fmt_dist(wrong, "m" if wrong < 1000 else "km")
        cases.append(GroundingCase("hallucinated", "distance_wrong", rooms, pref,
                                   _answer(rng, rooms, pf, af, dep, dist_override={rng.randrange(min(3, len(rooms))): shown}), ev))

    for _ in range(n_per_mutation):                                          # mã phòng bịa
        rooms, pref, pf, af, dep, ev = base()
        fake = f"nhatot_{rng.randint(10**8, 10**9 - 1)}"
        cases.append(GroundingCase("hallucinated", "id_fake", rooms, pref, _answer(rng, rooms, pf, af, dep) + f"\nXem thêm phòng {fake} nhé.", ev))

    for _ in range(n_per_mutation):                                          # số tiền (cọc) không có căn cứ
        rooms, pref, pf, af, dep, ev = base()
        wrong = _far(rng, refs_of(rooms, pref), 1_000_000, 9_000_000, 500_000, 400_000)
        cases.append(GroundingCase("hallucinated", "unsupported_deposit", rooms, pref,
                                   _answer(rng, rooms, pf, af, dep) + f"\nTiền cọc phòng Top 1 là {fmt_triệu(wrong)}.", ev))
    return cases
