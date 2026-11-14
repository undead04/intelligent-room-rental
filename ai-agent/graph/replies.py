"""Câu trả lời cố vấn thông minh & động khi không tìm thấy phòng trọ (Zero-result Advisory)."""

from __future__ import annotations

from typing import Any

from domain.enums import amenity_label
from domain.schemas import UserPreferenceState, format_vnd_million


def _format_nearby_bullets(pref: UserPreferenceState, search_args: dict[str, Any]) -> str:
    """Lấy danh sách khu vực lân cận động từ Backend API (/locations/nearby)."""
    from tools.housing_tools import fetch_nearby_locations

    lat = pref.lat or search_args.get("lat")
    lng = pref.lng or search_args.get("lng")
    district_id = pref.district_id or search_args.get("district_id")
    ward_id = pref.ward_id or search_args.get("ward_id")
    city_id = pref.city_id or search_args.get("city_id")
    min_price = pref.min_price or search_args.get("min_price")
    max_price = pref.max_price or search_args.get("max_price")
    raw_rt = (
        pref.allowed_room_types[0].value
        if len(pref.allowed_room_types) == 1
        else search_args.get("room_type")
    )
    room_type = raw_rt if isinstance(raw_rt, str) else None
    amenities = pref.amenities or search_args.get("amenities") or []
    amenity_list = [getattr(a, "value", str(a)) for a in amenities] if amenities else None

    items = []
    try:
        items = fetch_nearby_locations(
            lat=lat,
            lng=lng,
            district_id=district_id,
            ward_id=ward_id,
            city_id=city_id,
            radius_km=12.0,
            limit=3,
            min_price=min_price,
            max_price=max_price,
            room_type=room_type,
            amenities=amenity_list,
        )
    except Exception:
        items = []

    if items:
        lines = []
        for it in items:
            name = it.get("name")
            parent = it.get("parent_name")
            parent_suffix = f" ({parent})" if parent else ""
            dist = it.get("distance_km")
            cnt = it.get("total_listings")
            mn_val = it.get("min_price_vnd")
            mx_val = it.get("max_price_vnd")
            avg_val = it.get("avg_price_vnd")

            mn = format_vnd_million(mn_val) if mn_val else None
            mx = format_vnd_million(mx_val) if mx_val else None
            avg = format_vnd_million(avg_val) if avg_val else None

            if mn and mx and mn != mx:
                mn_clean = mn.replace("/tháng", "").strip()
                price_str = f"giá từ {mn_clean} – {mx}"
            elif mn:
                price_str = f"giá từ {mn}"
            else:
                price_str = "giá thỏa thuận"

            avg_str = f" (TB {avg})" if avg else ""
            label = "phòng phù hợp" if it.get("is_filtered") else "phòng trống"
            lines.append(f"     - **{name}{parent_suffix}**: cách {dist}km, hiện có {cnt} {label}, {price_str}{avg_str}")
        return "\n".join(lines)
    return ""


def reply_when_no_rooms(state: dict[str, Any], session: Any = None) -> str:
    pref = state.get("preferences") or UserPreferenceState()
    search_args = state.get("last_search_args") or {}

    # 1. Các trường hợp lỗi kỹ thuật / địa giới hành chính không tồn tại
    if state.get("search_error"):
        return "Xin lỗi bạn, Homigo đang gặp sự cố khi truy vấn dữ liệu phòng trọ. Bạn thử gửi lại sau ít phút nhé!"
    if state.get("admin_not_found"):
        loc = pref.location_text or "khu vực này"
        neighbor_str = _format_nearby_bullets(pref, search_args)
        return (
            f"Hiện tại Homigo chưa có dữ liệu phòng trọ tại khu vực **{loc}**.\n\n"
            f"💡 **Gợi ý các khu vực lân cận giáp ranh có nhiều phòng trống:**\n{neighbor_str}\n\n"
            "👉 Bạn có muốn Homigo tìm phòng ở một trong các khu vực trên không? Hãy nhắn cho mình biết nhé!"
        )
    cands = state.get("ambiguous_candidates") or []
    if cands:
        names = ", ".join(str(c.get("name")) for c in cands[:5] if c.get("name"))
        return f"**{pref.location_text}** có nhiều nơi trùng tên ({names}). Bạn cho Homigo biết cụ thể thuộc quận/thành phố nào nhé?"

    market = state.get("market_context")
    loc = (market.area_name if market and market.area_name else None) or pref.location_text or "khu vực bạn chọn"
    user_max = pref.max_price
    user_budget_str = market.user_budget_str if market and market.user_budget_str else (format_vnd_million(user_max) if user_max else None)
    min_p_val = market.market_min_price if market else None
    avg_p_val = market.market_avg_price if market else None
    min_p_str = market.market_min_price_str if market else (format_vnd_million(min_p_val) if min_p_val else None)
    avg_p_str = market.market_avg_price_str if market else (format_vnd_million(avg_p_val) if avg_p_val else None)

    neighbor_bullets = _format_nearby_bullets(pref, search_args)

    # CASE A: NGÂN SÁCH QUÁ CAO (Luxury Gap / Over-budget)
    is_luxury = user_max is not None and (
        user_max >= 9_000_000
        or (avg_p_val is not None and user_max > avg_p_val * 2.3)
    )
    if is_luxury:
        mkt_avg_line = f" (mức giá thuê trung bình tại đây chỉ khoảng **{avg_p_str}**)" if avg_p_str else ""

        return (
            f"Homigo hiện chưa tìm thấy phòng trọ nào khớp với ngân sách **{user_budget_str}** tại **{loc}**.\n\n"
            f"📊 **Nhận định thị trường tại {loc}:**\n"
            f"- Ngân sách **{user_budget_str}** của bạn thuộc phân khúc **ngân sách lớn / căn hộ cao cấp**.\n"
            f"- Tuy nhiên, tại khu vực **{loc}**, nguồn tin đăng chủ yếu phục vụ sinh viên và người đi làm phổ thông{mkt_avg_line}, nên hầu như không có phòng trọ truyền thống ở tầm giá cao như vậy.\n\n"
            f"💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**\n"
            f"  1. **Hạ mức trần tìm kiếm:** Nếu bạn muốn thuê tại **{loc}**, bạn chỉ cần mức ngân sách khoảng **{format_vnd_million(avg_p_val * 1.4) if avg_p_val else '4 – 6 triệu/tháng'}** là đã có thể chọn được các căn studio / căn hộ mini mới xây đẹp nhất khu vực rồi.\n"
            f"  2. **Chuyển sang các khu vực tập trung nhiều căn hộ cao cấp:** Với ngân sách thoải mái này, bạn có thể tham khảo các khu đô thị và chung cư hiện đại lân cận như:\n{neighbor_bullets}\n"
            f"  3. **Mở rộng loại hình:** Bạn có thể thử tìm kiếm với từ khóa *'căn hộ dịch vụ'* hoặc *'chung cư mini'* thay vì phòng trọ.\n\n"
            "👉 Bạn muốn Homigo tìm căn hộ cao cấp ở các khu vực lân cận trên, hay muốn hạ mức giá xuống để xem phòng đẹp nhất tại khu này? Nhắn cho mình biết nhé!"
        )

    # CASE B: NGÂN SÁCH QUÁ THẤP (Under-budget / Market Gap)
    is_under_budget = bool(market and market.is_market_gap) or (
        user_max is not None and min_p_val is not None and user_max < min_p_val
    )
    if is_under_budget and min_p_str:
        avg_line = f"\n  - **Mức giá phổ biến (trung bình):** khoảng **{avg_p_str}**" if avg_p_str else ""
        user_line = f"\n  - **Ngân sách của bạn:** **{user_budget_str}** (hiện thấp hơn đáng kể so với giá sàn thực tế tại đây)" if user_budget_str else ""

        suggestions = [
            f"  1. **Điều chỉnh ngân sách:** Cân nhắc nâng ngân sách lên từ khoảng **{min_p_str}** để có thể tiếp cận phòng riêng cơ bản tại {loc}."
        ]
        has_dorm = user_max is not None and user_max <= 2_000_000
        if has_dorm:
            suggestions.append(
                "  2. **Ký túc xá / Sleepbox:** Nếu cần tối ưu chi phí trong tầm giá này, mô hình Ký túc xá cao cấp hoặc Sleepbox là lựa chọn rất khả thi (thường có giá từ 1.2 – 1.8 triệu/tháng)."
            )
            suggestions.append(
                f"  3. **Mở rộng sang các khu vực lân cận có mặt bằng giá mềm hơn:**\n{neighbor_bullets}"
            )
        else:
            suggestions.append(
                f"  2. **Mở rộng sang các khu vực lân cận có mặt bằng giá mềm hơn:**\n{neighbor_bullets}"
            )
            suggestions.append(
                "  3. **Lược bớt tiện ích:** Giảm bớt một số tiện ích khắt khe nếu có để tiếp cận các phòng trọ cơ bản."
            )
        sug_block = "\n".join(suggestions)

        return (
            f"Homigo hiện chưa tìm thấy phòng trọ nào khớp với các điều kiện lọc của bạn tại **{loc}**.\n\n"
            f"📊 **Thông tin mặt bằng giá thực tế tại {loc}:**\n"
            f"  - **Giá thuê thấp nhất (giá sàn):** từ **{min_p_str}**{avg_line}{user_line}\n\n"
            f"💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**\n{sug_block}\n\n"
            "👉 Bạn muốn điều chỉnh theo hướng nào (nâng ngân sách, tìm sleepbox hay đổi sang khu vực lân cận nào ở trên)? Hãy nhắn cho Homigo biết nhé!"
        )

    # CASE C: NGÂN SÁCH PHÙ HỢP NHƯNG 0 PHÒNG (Do Tiện ích khắt khe / Loại phòng)
    amenities = pref.amenities or []
    if len(amenities) >= 2:
        amenity_names = ", ".join(amenity_label(a) for a in amenities)
        avg_line = f" (mặt bằng trung bình tại đây khoảng **{avg_p_str}**)" if avg_p_str else ""
        return (
            f"Homigo hiện chưa tìm thấy phòng trọ nào tại **{loc}** đáp ứng đầy đủ tất cả tiêu chí của bạn.\n\n"
            f"📊 **Phân tích nguyên nhân:**\n"
            f"- Mức ngân sách **{user_budget_str or 'của bạn'}** thực tế rất phù hợp với khu vực này{avg_line}.\n"
            f"- Tuy nhiên, bạn đang yêu cầu đồng thời nhiều tiện ích bắt buộc: **{amenity_names}**. Trong phân khúc phòng trọ cho thuê, việc một căn phòng hội tụ đủ 100% các tiêu chí trên thường khá hiếm hoặc phòng đã có người thuê trước.\n\n"
            f"💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**\n"
            f"  1. **Lược bớt tiện ích phụ:** Bạn có thể giữ lại tiện ích quan trọng nhất (như máy lạnh) và tạm thời lược bớt các tiêu chí khác (như máy giặt riêng, nuôi pet, khoá vân tay) để có thêm nhiều lựa chọn.\n"
            f"  2. **Mở rộng sang các khu vực lân cận có nhiều phòng mới xây:**\n{neighbor_bullets}\n\n"
            "👉 Bạn có muốn Homigo tìm phòng có tiện ích nào quan trọng nhất trước, hay muốn mở rộng sang khu vực lân cận nào? Hãy nhắn cho mình biết nhé!"
        )

    # CASE D: PHẠM VI QUÁ HẸP (Giới hạn trong 1 phường) HOẶC PHÒNG TẠM THỜI HẾT
    is_narrow_ward = pref.ward_id is not None or search_args.get("ward_id") is not None
    if is_narrow_ward:
        return (
            f"Homigo hiện chưa tìm thấy phòng trọ nào khớp với tiêu chí trong phạm vi phường hiện tại ở **{loc}**.\n\n"
            f"💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**\n"
            f"  1. **Mở rộng phạm vi tìm kiếm:** Bạn có thể mở rộng tìm kiếm ra toàn Quận/Huyện hoặc các khu vực lân cận giáp ranh:\n{neighbor_bullets}\n"
            f"  2. **Nới nhẹ ngân sách:** Cân nhắc nâng ngân sách lên khoảng **{min_p_str or 'mức giá phù hợp hơn'}** để tiếp cận các phòng mới đăng tải.\n\n"
            "👉 Bạn có muốn Homigo mở rộng tìm kiếm ra toàn quận hay sang khu vực lân cận nào ở trên không? Hãy nhắn cho mình biết nhé!"
        )

    return (
        f"Homigo hiện chưa tìm thấy phòng trọ nào khớp 100% với điều kiện lọc của bạn tại **{loc}**.\n\n"
        f"💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**\n"
        f"  1. **Mở rộng sang các khu vực lân cận có nhiều nguồn phòng hơn:**\n{neighbor_bullets}\n"
        f"  2. **Điều chỉnh ngân sách hoặc tiện ích:** Cân nhắc nâng ngân sách lên khoảng **{min_p_str or 'mức giá phù hợp hơn'}** hoặc lược bớt một số yêu cầu khắt khe.\n\n"
        "👉 Bạn muốn điều chỉnh lại mức giá, tiện ích hay muốn đổi sang khu vực lân cận nào? Hãy nhắn cho Homigo biết nhé!"
    )
