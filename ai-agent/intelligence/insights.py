"""Phân tích hỗ trợ quyết định + câu trả lời mẫu, hoàn toàn bằng code (không LLM). Port từ graph, đã sửa:
  - dùng match_percent thay vì in matchScore thô (0.87);
  - mọi con số do code tính từ dữ liệu phòng nên luôn khớp bộ kiểm grounding;
  - thêm chênh lệch diện tích (grounding đã nhận chênh lệch diện tích giữa mọi cặp).
"""

from __future__ import annotations

from typing import Optional, Sequence

from domain.schemas import DecisionInsight, RoomItem, TradeOffAnalysis

FACTOR_VN = {
    "price": "Mức giá tối ưu",
    "location": "Vị trí gần điểm mong muốn",
    "amenity": "Đáp ứng nhiều tiện nghi",
    "safety": "Điểm an ninh khu vực cao",
    "semantic": "Khớp sát mô tả ngữ nghĩa",
}
DEFAULT_CHECKLIST = [
    "Xác nhận lại chi phí điện nước và phí dịch vụ phát sinh (gửi xe, rác, internet).",
    "Kiểm tra thực tế tình trạng cách âm và an ninh dãy trọ (camera, cổng khoá).",
    "Xác nhận lại với chủ nhà về hợp đồng cọc và giờ giấc ra vào.",
]


def fmt_money_short(v: float) -> str:
    """400000 -> '400k'; 1_250_000 -> '1.25 triệu' (parse_vnd_amounts đọc lại đúng giá trị)."""
    v = abs(v)
    if v >= 1_000_000:
        return f"{v / 1_000_000:.2f}".rstrip("0").rstrip(".") + " triệu"
    return f"{round(v / 1000)}k"


def price_trade_off(a: RoomItem, b: RoomItem) -> str:
    """So sánh giá + diện tích a so với b, tính bằng code. '' nếu thiếu dữ liệu."""
    parts: list[str] = []
    if a.priceNum > 0 and b.priceNum > 0:
        d = a.priceNum - b.priceNum
        if abs(d) < 10_000:
            parts.append(f"Top {a.rank} và Top {b.rank} có cùng mức giá")
        else:
            parts.append(f"Top {a.rank} {'rẻ' if d < 0 else 'đắt'} hơn Top {b.rank} khoảng {fmt_money_short(d)}/tháng")
    if a.area_m2 and b.area_m2 and abs(a.area_m2 - b.area_m2) >= 1:
        d = a.area_m2 - b.area_m2
        parts.append(f"{'rộng' if d > 0 else 'nhỏ'} hơn {abs(d):g} m²")
    return (", ".join(parts) + ".") if parts else ""


def build_decision_insights(
    rooms: Sequence[RoomItem],
    weights: Optional[dict[str, float]] = None,
    weight_explanations: Optional[Sequence[str]] = None,
) -> Optional[DecisionInsight]:
    if not rooms:
        return None
    top1 = rooms[0]
    explain = top1.explain_match or {}
    key_factors = [FACTOR_VN[f["name"]] for f in (explain.get("top_factors") or []) if f.get("name") in FACTOR_VN][:3]
    reason = [f"Phòng được xếp hạng Top 1 nhờ đạt điểm phù hợp cao nhất ({top1.match_percent}%)."]
    if key_factors:
        reason.append(f"Các yếu tố nổi bật: {', '.join(key_factors)}.")
    if weight_explanations:
        reason.append(f"Hệ thống đã ưu tiên theo nhu cầu của bạn: {', '.join(weight_explanations)}.")

    trade_offs: list[TradeOffAnalysis] = []
    if len(rooms) > 1:
        top2 = rooms[1]
        d = top1.priceNum - top2.priceNum if top1.priceNum > 0 and top2.priceNum > 0 else 0
        line = price_trade_off(top1, top2)
        if d < 0:
            adv, dis = f"Điểm phù hợp cao hơn ({top1.match_percent}% so với {top2.match_percent}%) và giá thấp hơn. {line}".strip(), f"Top 2 ({top2.title[:30]}...) có thể có vị trí hoặc tiện nghi khác biệt."
        elif d > 0:
            adv, dis = f"Điểm phù hợp cao hơn ({top1.match_percent}% so với {top2.match_percent}%) nhờ đáp ứng tốt các tiêu chí ưu tiên.", f"Giá thuê cao hơn Top 2. {line}".strip()
        else:
            adv, dis = f"Điểm phù hợp cao hơn ({top1.match_percent}% so với {top2.match_percent}%). {line}".strip(), f"Top 2 ({top2.title[:30]}...) có thể có diện tích hoặc tiện nghi khác biệt."
        trade_offs.append(TradeOffAnalysis(compared_with=f"Top 2 ({top2.title[:35]}...)", advantage=adv, disadvantage=dis))

    return DecisionInsight(
        selected_top_1_id=top1.id, top_1_reason=" ".join(reason), key_factors=key_factors,
        trade_offs=trade_offs, verification_checklist=list(DEFAULT_CHECKLIST),
    )


def room_lines(r: RoomItem) -> list[str]:
    lines = [f"{r.rank}. **{r.title}**", f"   - Giá thuê: {r.price}"]
    if r.address:
        lines.append(f"   - Địa chỉ: {r.address}")
    if r.area_m2:
        lines.append(f"   - Diện tích: {r.area_m2:g} m²")
    lines.append(f"   - Điểm phù hợp: {r.match_percent}%")
    if r.distance:
        lines.append(f"   - Cách điểm tìm kiếm: {r.distance}")
    return lines


def template_reply(rooms: Sequence[RoomItem], insights: Optional[DecisionInsight], max_rooms: int = 3) -> str:
    """Câu trả lời 100% bằng code: lưới an toàn cuối cùng khi LLM lỗi hoặc grounding thất bại nhiều lần."""
    top1 = rooms[0]
    lines = [f"Homigo đã tìm được {len(rooms)} phòng phù hợp nhất với nhu cầu của bạn:", ""]
    for r in rooms[:max_rooms]:
        lines.extend(room_lines(r))
    lines.extend(["", f"🏆 **Lựa chọn tối ưu nhất: {top1.title}**"])
    if insights and insights.top_1_reason:
        lines.append(f"- {insights.top_1_reason}")
    if len(rooms) > 1 and insights and insights.trade_offs:
        t = insights.trade_offs[0]
        lines.extend(["", f"⚖️ **So với {t.compared_with}:** {t.advantage}"])
    checklist = (insights.verification_checklist if insights else None) or DEFAULT_CHECKLIST
    lines.extend(["", "📋 **Lưu ý khi đi xem phòng:**", *[f"- {c}" for c in checklist[:3]]])
    return "\n".join(lines)
