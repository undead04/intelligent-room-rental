"""Câu trả lời cố vấn thông minh & động khi không tìm thấy phòng trọ (Zero-result Advisory)."""

from __future__ import annotations

from typing import Any, Optional

from domain.enums import HitlAction, amenity_label
from domain.schemas import UserPreferenceState, format_vnd_million
from utils.text import strip_accents

MAX_HITL_STREAK = 2

# Bản đồ khu vực lân cận dự phòng khi Backend chưa có toạ độ (fallback heuristic)
_NEIGHBOR_MAP: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("uit", "cntt", "cong nghe thong tin", "dhqg", "lang dai hoc", "ktx khu b", "ktx khu a", "dai hoc quoc gia"),
        [
            "Phường Đông Hòa (TP. Dĩ An - ngay sát KTX Khu B, nhiều phòng sinh viên 1.5 - 2.5 triệu/tháng)",
            "Phường Linh Trung (TP. Thủ Đức - cách trường 1-2km, rất thuận tiện tuyến xe buýt số 8, 10, 53)",
            "Phường Linh Xuân (TP. Thủ Đức - trục Quốc lộ 1K, giá phòng mềm hơn)",
            "Khu vực Tăng Nhơn Phú (Quận 9 cũ - nhiều tiện ích ăn uống, sinh hoạt sinh viên)",
        ],
    ),
    (
        ("di an", "dong hoa", "tan dong hiep", "an binh"),
        [
            "Phường Linh Xuân (TP. Thủ Đức - giáp ranh Quốc lộ 1K, nhiều phòng có gác lửng)",
            "Phường Linh Trung (TP. Thủ Đức - giáp ranh khu Làng Đại Học)",
            "TP. Thuận An (khu vực An Phú, Lái Thiêu - giáp ranh, mặt bằng giá tương đương)",
            "Khu vực KTX Khu B ĐHQG (nhiều phòng trọ sinh viên mức giá 1.8 - 2.8 triệu/tháng)",
        ],
    ),
    (
        ("thuan an", "lai thieu", "an phu"),
        [
            "TP. Dĩ An (khu vực Tân Đông Hiệp, An Bình - giáp ranh)",
            "Quận 12 (khu An Phú Đông, Thạnh Lộc - qua cầu Phú Long)",
            "TP. Thủ Đức (khu Hiệp Bình Phước, Tam Bình dọc Quốc lộ 13)",
        ],
    ),
    (
        ("thu duc", "tp thu duc", "linh trung", "linh tay", "linh xuan", "hiep binh"),
        [
            "TP. Dĩ An (Bình Dương - giá mềm hơn 20-30%, di chuyển chỉ 10-15 phút)",
            "Khu vực Quận 9 cũ (Hiệp Phú, Tăng Nhơn Phú - không gian thoáng, nhiều phòng mới)",
            "Bình Thạnh (khu Thanh Đa, Bình Quới - thuận tiện nếu cần đi vào trung tâm)",
            "Phường Tam Bình, Hiệp Bình Phước (trục Quốc lộ 13 / Phạm Văn Đồng)",
        ],
    ),
    (
        ("quan 9", "q9", "tang nhon phu", "long truong", "phuoc long", "hiep phu"),
        [
            "Khu vực Thủ Đức cũ (Linh Trung, Trường Thọ)",
            "TP. Dĩ An (giáp ranh Khu Công nghệ cao và Xa lộ Hà Nội)",
            "Phường Long Thạnh Mỹ (gần Vinhomes Grand Park, nhiều căn hộ studio)",
        ],
    ),
    (
        ("quan 1", "q1", "ben nghe", "ben thanh", "da kao", "tan dinh"),
        [
            "Quận 4 (khu Bến Vân Đồn, Tôn Đản - chỉ qua cầu Calmette/Khánh Hội, giá mềm hơn 25-35%)",
            "Bình Thạnh (khu Đa Kao / Thị Nghè - cách Q1 chỉ 5 phút xe máy, nhiều phòng studio mini)",
            "Quận 3 (khu ga Sài Gòn, bờ kè Nhiêu Lộc - trung tâm nhưng giá thuê dễ thở hơn)",
            "Phú Nhuận (khu Phan Xích Long, Hoàng Sa)",
        ],
    ),
    (
        ("quan 3", "q3"),
        [
            "Quận 10 (khu Tô Hiến Thành, Cách Mạng Tháng 8 - giá mềm hơn)",
            "Phú Nhuận (khu bờ kè Lê Văn Sỹ, Huỳnh Văn Bánh)",
            "Tân Bình (khu Bảy Hiền, Lê Thị Riêng)",
        ],
    ),
    (
        ("quan 4", "q4"),
        [
            "Quận 7 (khu Him Lam, Tân Hưng - chỉ qua cầu Kênh Tẻ)",
            "Quận 8 (khu Hưng Phú, cầu Chữ Y)",
            "Quận 1 (khu Bến Vân Đồn)",
        ],
    ),
    (
        ("quan 7", "q7", "tan phong", "tan phu", "phu my hung"),
        [
            "Huyện Nhà Bè (khu Phước Kiển, Lê Văn Lương - ngay sát ranh Q7, giá rẻ hơn từ 1 – 2 triệu/tháng)",
            "Quận 8 (khu Trung Sơn, đường Phạm Hùng - tiện qua cầu Him Lam)",
            "Quận 4 (khu Tôn Thất Thuyết, Bến Vân Đồn)",
        ],
    ),
    (
        ("nha be", "phuoc kien"),
        [
            "Quận 7 (khu Tân Phong, Tân Quy, Phú Mỹ)",
            "Bình Chánh (khu Phong Phú, Đa Phước)",
            "Quận 8 (khu Tạ Quang Bửu, Phạm Hùng)",
        ],
    ),
    (
        ("binh thanh", "hang xanh", "thi nghe", "thanh da"),
        [
            "Gò Vấp (khu ngã năm Chu Văn An, Phan Văn Trị - giá mềm hơn đáng kể, nhiều phòng rộng)",
            "Phú Nhuận (khu Phan Xích Long, Nguyễn Văn Đậu)",
            "TP. Thủ Đức (khu Hiệp Bình Chánh, đường Phạm Văn Đồng)",
        ],
    ),
    (
        ("go vap", "phan van tri", "quang trung"),
        [
            "Quận 12 (khu An Phú Đông, Thạnh Lộc - ngay qua cầu An Phú Đông, giá rẻ hơn 30%)",
            "Bình Thạnh (khu Phạm Văn Đồng, Chu Văn An)",
            "Tân Bình (khu Quang Trung, Phạm Văn Bạch, Hoàng Hoa Thám)",
        ],
    ),
    (
        ("tan binh", "bay hien", "cong hoa", "hoang hoa tham"),
        [
            "Tân Phú (khu Lũy Bán Bích, Thoại Ngọc Hầu - cùng phân khúc nhưng giá mềm hơn 15-20%)",
            "Gò Vấp (khu Phạm Văn Bạch, Quang Trung)",
            "Quận 10 (khu Bắc Hải, Lý Thường Kiệt)",
        ],
    ),
    (
        ("tan phu", "luy ban bich", "hoa thanh"),
        [
            "Bình Tân (khu Tên Lửa, Lê Trọng Tấn - nhiều phòng mới xây, giá rất hợp lý)",
            "Tân Bình (khu Bàu Cát, Âu Cơ)",
            "Quận 11 (khu Đầm Sen, Lạc Long Quân)",
        ],
    ),
    (
        ("binh tan", "ten lua", "an lac"),
        [
            "Tân Phú (khu Tân Kỳ Tân Quý, Bình Long)",
            "Quận 6 (khu Bến xe Miền Tây, Kinh Dương Vương)",
            "Bình Chánh (khu Vĩnh Lộc, Tân Kiên - giá rất rẻ)",
        ],
    ),
    (
        ("quan 10", "q10", "quan 11", "q11", "quan 5", "q5"),
        [
            "Quận 11 (khu Lữ Gia, Đầm Sen - giá mềm hơn Quận 10 từ 15-20%)",
            "Tân Bình (khu Lý Thường Kiệt, Bảy Hiền)",
            "Quận 8 (khu cầu Chà Và, Tạ Quang Bửu - giá tốt hơn nhiều)",
        ],
    ),
    (
        ("quan 12", "q12", "hoc mon", "an phu dong", "thanh loc"),
        [
            "Gò Vấp (khu Nguyễn Oanh, Quang Trung - tiện nghi đầy đủ hơn)",
            "Huyện Hóc Môn (khu Bà Điểm, ngã tư An Sương - giá rất rẻ)",
            "TP. Thuận An (khu Lái Thiêu - qua cầu Phú Long)",
        ],
    ),
]

_LUXURY_NEIGHBORS = [
    "TP. Thủ Đức (khu Thảo Điền, An Phú, Sala - nhiều căn hộ dịch vụ cao cấp, studio view đẹp)",
    "Bình Thạnh (khu Vinhomes Central Park, The Manor, dọc trục Nguyễn Hữu Cảnh)",
    "Quận 7 (khu đô thị Phú Mỹ Hưng, đường Nguyễn Lương Bằng, Sunrise City)",
]


def _get_neighboring_areas(location_text: Optional[str] = None) -> list[str]:
    """Tìm danh sách 2-3 khu vực lân cận dự phòng theo từ khoá."""
    if not location_text:
        return [
            "TP. Dĩ An (Bình Dương - giá mềm cho sinh viên/người đi làm)",
            "TP. Thủ Đức (khu vực Linh Trung, Linh Xuân, Tăng Nhơn Phú)",
            "Bình Thạnh / Gò Vấp (khu vực giáp ranh Phạm Văn Đồng)",
        ]

    clean = strip_accents(str(location_text)).lower()
    for keys, neighbors in _NEIGHBOR_MAP:
        if any(k in clean for k in keys):
            return neighbors[:3]

    return [
        "Khu vực giáp ranh trong bán kính 3-5km",
        "Các phường lân cận cùng thuộc Quận/Huyện",
        "Khu vực Dĩ An / Thủ Đức dọc trục Phạm Văn Đồng",
    ]


def _format_nearby_bullets(loc: str, pref: UserPreferenceState, search_args: dict[str, Any]) -> str:
    """Lấy danh sách khu vực lân cận động từ Backend API (/locations/nearby); fallback sang heuristic nếu offline."""
    from tools.housing_tools import fetch_nearby_locations

    lat = pref.lat or search_args.get("lat")
    lng = pref.lng or search_args.get("lng")
    district_id = pref.district_id or search_args.get("district_id")
    ward_id = pref.ward_id or search_args.get("ward_id")
    city_id = pref.city_id or search_args.get("city_id")
    min_price = pref.min_price or search_args.get("min_price")
    max_price = pref.max_price or search_args.get("max_price")
    room_type = pref.room_type or search_args.get("room_type")
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

    neighbors = _get_neighboring_areas(loc)
    return "\n".join(f"     - {n}" for n in neighbors[:3])


def reply_when_no_rooms(state: dict[str, Any], session: Any) -> str:
    pref = state.get("preferences") or UserPreferenceState()
    search_args = state.get("last_search_args") or {}

    # 1. Các trường hợp lỗi kỹ thuật / địa giới hành chính không tồn tại
    if state.get("search_error"):
        return "Xin lỗi bạn, Homigo đang gặp sự cố khi truy vấn dữ liệu phòng trọ. Bạn thử gửi lại sau ít phút nhé!"
    if state.get("admin_not_found"):
        loc = pref.location_text or "khu vực này"
        neighbor_str = _format_nearby_bullets(loc, pref, search_args)
        return (
            f"Hiện tại Homigo chưa có dữ liệu phòng trọ tại khu vực **{loc}**.\n\n"
            f"💡 **Gợi ý các khu vực lân cận giáp ranh có nhiều phòng trống:**\n{neighbor_str}\n\n"
            "👉 Bạn có muốn Homigo tìm phòng ở một trong các khu vực trên không? Hãy nhắn cho mình biết nhé!"
        )
    cands = state.get("ambiguous_candidates") or []
    if cands:
        names = ", ".join(str(c.get("name")) for c in cands[:5] if c.get("name"))
        return f"**{pref.location_text}** có nhiều nơi trùng tên ({names}). Bạn cho Homigo biết cụ thể thuộc quận/thành phố nào nhé?"
    if session.hitl_streak > MAX_HITL_STREAK:
        neighbor_str = _format_nearby_bullets(pref.location_text or "", pref, search_args)
        return (
            "Homigo đã hỗ trợ nới lỏng nhiều tiêu chí nhưng hiện chưa tìm thấy phòng trọ nào khớp với mong muốn.\n\n"
            f"💡 **Gợi ý bạn có thể đổi hướng sang các khu vực lân cận:**\n{neighbor_str}\n\n"
            "👉 Bạn muốn thử tìm ở khu vực nào, hoặc muốn điều chỉnh ngân sách thế nào? Nhắn cho Homigo biết nhé!"
        )

    hitl = state.get("hitl_proposal")
    loc = (hitl.area_name if hitl and hitl.area_name else None) or pref.location_text or "khu vực bạn chọn"
    user_max = pref.max_price
    user_budget_str = hitl.user_budget_str if hitl and hitl.user_budget_str else (format_vnd_million(user_max) if user_max else None)
    min_p_val = hitl.market_min_price if hitl else None
    avg_p_val = hitl.market_avg_price if hitl else None
    min_p_str = hitl.market_min_price_str if hitl else (format_vnd_million(min_p_val) if min_p_val else None)
    avg_p_str = hitl.market_avg_price_str if hitl else (format_vnd_million(avg_p_val) if avg_p_val else None)
    prop_p_str = hitl.proposed_budget_str if hitl and hitl.proposed_budget_str else (format_vnd_million(user_max * 1.15) if user_max else None)

    neighbor_bullets = _format_nearby_bullets(loc, pref, search_args)

    # --------------------------------------------------------------------------
    # CASE A: NGÂN SÁCH QUÁ CAO (Luxury Gap / Over-budget)
    # Ví dụ: 15-20 triệu ở khu vực sinh viên / giá rẻ như Dĩ An, Thủ Đức bình dân
    # --------------------------------------------------------------------------
    is_luxury = user_max is not None and (
        user_max >= 9_000_000
        or (avg_p_val is not None and user_max > avg_p_val * 2.3)
    )
    if is_luxury:
        lux_bullets = "\n".join(f"     - {n}" for n in _LUXURY_NEIGHBORS[:3])
        mkt_avg_line = f" (mức giá thuê trung bình tại đây chỉ khoảng **{avg_p_str}**)" if avg_p_str else ""

        return (
            f"Homigo hiện chưa tìm thấy phòng trọ nào khớp với ngân sách **{user_budget_str}** tại **{loc}**.\n\n"
            f"📊 **Nhận định thị trường tại {loc}:**\n"
            f"- Ngân sách **{user_budget_str}** của bạn thuộc phân khúc **ngân sách lớn / căn hộ cao cấp**.\n"
            f"- Tuy nhiên, tại khu vực **{loc}**, nguồn tin đăng chủ yếu phục vụ sinh viên và người đi làm phổ thông{mkt_avg_line}, nên hầu như không có phòng trọ truyền thống ở tầm giá cao như vậy.\n\n"
            f"💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**\n"
            f"  1. **Hạ mức trần tìm kiếm:** Nếu bạn muốn thuê tại **{loc}**, bạn chỉ cần mức ngân sách khoảng **{format_vnd_million(avg_p_val * 1.4) if avg_p_val else '4 – 6 triệu/tháng'}** là đã có thể chọn được các căn studio / căn hộ mini mới xây đẹp nhất khu vực rồi.\n"
            f"  2. **Chuyển sang các khu vực tập trung nhiều căn hộ cao cấp:** Với ngân sách thoải mái này, bạn có thể tham khảo các khu đô thị và chung cư hiện đại lân cận như:\n{lux_bullets}\n"
            f"  3. **Mở rộng loại hình:** Bạn có thể thử tìm kiếm với từ khóa *'căn hộ dịch vụ'* hoặc *'chung cư mini'* thay vì phòng trọ.\n\n"
            "👉 Bạn muốn Homigo tìm căn hộ cao cấp ở các khu vực lân cận trên, hay muốn hạ mức giá xuống để xem phòng đẹp nhất tại khu này? Nhắn cho mình biết nhé!"
        )

    # --------------------------------------------------------------------------
    # CASE B: NGÂN SÁCH QUÁ THẤP (Under-budget / Market Gap)
    # Ví dụ: 1.5 triệu ở khu vực có giá sàn 2.2 triệu
    # --------------------------------------------------------------------------
    is_under_budget = bool(hitl and hitl.is_market_gap) or (
        user_max is not None and min_p_val is not None and user_max < min_p_val * 0.95
    )
    if is_under_budget and min_p_str:
        avg_line = f"\n  - **Mức giá phổ biến (trung bình):** khoảng **{avg_p_str}**" if avg_p_str else ""
        user_line = f"\n  - **Ngân sách của bạn:** **{user_budget_str}** (hiện thấp hơn đáng kể so với giá sàn thực tế tại đây)" if user_budget_str else ""

        suggestions = [
            f"  1. **Điều chỉnh ngân sách:** Cân nhắc nâng ngân sách lên từ khoảng **{prop_p_str or min_p_str}** để có thể tiếp cận phòng riêng cơ bản tại {loc}."
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

    # --------------------------------------------------------------------------
    # CASE C: NGÂN SÁCH PHÙ HỢP NHƯNG 0 PHÒNG (Do Tiện ích khắt khe / Loại phòng)
    # --------------------------------------------------------------------------
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

    # --------------------------------------------------------------------------
    # CASE D: PHẠM VI QUÁ HẸP (Giới hạn trong 1 phường) HOẶC PHÒNG TẠM THỜI HẾT
    # --------------------------------------------------------------------------
    is_narrow_ward = pref.ward_id is not None or search_args.get("ward_id") is not None
    if is_narrow_ward:
        return (
            f"Homigo hiện chưa tìm thấy phòng trọ nào khớp với tiêu chí trong phạm vi phường hiện tại ở **{loc}**.\n\n"
            f"💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**\n"
            f"  1. **Mở rộng phạm vi tìm kiếm:** Bạn có thể mở rộng tìm kiếm ra toàn Quận/Huyện hoặc các khu vực lân cận giáp ranh:\n{neighbor_bullets}\n"
            f"  2. **Nới nhẹ ngân sách:** Cân nhắc nâng ngân sách lên khoảng **{prop_p_str or 'thêm 10-15%'}** để tiếp cận các phòng mới đăng tải.\n\n"
            "👉 Bạn có muốn Homigo mở rộng tìm kiếm ra toàn quận hay sang khu vực lân cận nào ở trên không? Hãy nhắn cho mình biết nhé!"
        )

    # Fallback tự nhiên chung
    return (
        f"Homigo hiện chưa tìm thấy phòng trọ nào khớp 100% với điều kiện lọc của bạn tại **{loc}**.\n\n"
        f"💡 **Gợi ý định hướng từ Homigo để bạn cân nhắc:**\n"
        f"  1. **Mở rộng sang các khu vực lân cận có nhiều nguồn phòng hơn:**\n{neighbor_bullets}\n"
        f"  2. **Điều chỉnh ngân sách hoặc tiện ích:** Cân nhắc nâng ngân sách lên khoảng **{prop_p_str or 'thêm 10-15%'}** hoặc lược bớt một số yêu cầu khắt khe.\n\n"
        "👉 Bạn muốn điều chỉnh lại mức giá, tiện ích hay muốn đổi sang khu vực lân cận nào? Hãy nhắn cho Homigo biết nhé!"
    )
