import pytest

from domain.enums import HitlAction
from intelligence.nlu_fallback import detect_hitl_action, detect_room_followup, detect_vague_location, legacy_analysis


@pytest.mark.parametrize("text,pending,expected", [
    ("👍 Đồng ý nới ngân sách lên 3.5 triệu (+15%)", False, HitlAction.RELAX_BUDGET),
    ("❌ Giữ nguyên tiêu chí của tôi", True, HitlAction.KEEP),
    ("🛌 Tìm ký túc xá", False, HitlAction.DORMITORY),
    ("✏️ Tùy chỉnh tiêu chí (Nhập thông tin mới)", True, HitlAction.CUSTOM),
    ("tuy chinh tieu chi", False, HitlAction.CUSTOM),
    ("giữ nguyên nhé", True, HitlAction.KEEP),
    ("không nới đâu", True, HitlAction.KEEP),            # 'không nới' phải thắng 'nới ngân sách'
    ("đồng ý nới ngân sách", True, HitlAction.RELAX_BUDGET),
    ("mở rộng ra lân cận đi", True, HitlAction.BROADEN),
    ("mở rộng ra lân cận đi", False, None),              # không có HITL treo -> không đoán
    ("x" * 100 + " giữ nguyên", True, None),
    ("", True, None),
])
def test_hitl(text, pending, expected):
    assert detect_hitl_action(text, pending) is expected


@pytest.mark.parametrize("text,has_rooms,expected", [
    ("so sánh top 1 và top 2", True, (True, 1)),
    ("phòng 3 có gác không", True, (True, 3)),
    ("cho mình sdt chủ nhà", True, (True, None)),
    ("so sánh top 1", False, (False, None)),
    ("tìm thêm phòng khác, so sánh giá", True, (False, None)),
    ("xem phòng được không", True, (False, None)),
])
def test_followup(text, has_rooms, expected):
    assert detect_room_followup(text, has_rooms) == expected


@pytest.mark.parametrize("text,expected", [
    ("gần khu công nghiệp", (True, "khu công nghiệp", None)),
    ("Tìm phòng gần KCN ở Bình Dương", (True, "khu công nghiệp", "binh duong")),
    ("gan truong", (True, "trường học", None)),            # không dấu
    ("gần bệnh viện tại Thủ Đức", (True, "bệnh viện", "thu duc")),
    ("gần KCN VSIP 1", (False, None, None)),                # đã có tên riêng
    ("phòng ở Quận 7", (False, None, None)),
])
def test_vague(text, expected):
    assert detect_vague_location(text) == expected


def test_legacy_analysis_flow():
    a = legacy_analysis("tìm phòng giá rẻ gần UIT", has_rooms=False, hitl_pending=False, has_history=False)
    assert a.intent == "new_search" and a.priorities.price == "high" and a.priorities.location == "high"
    assert a.priorities.safety is None and a.priority_reasons
    b = legacy_analysis("giá rẻ", has_rooms=True, hitl_pending=False, has_history=True)
    assert b.intent == "refine_search"
    c = legacy_analysis("gần khu công nghiệp", has_rooms=False, hitl_pending=False, has_history=False)
    assert c.patch.location_is_vague and c.patch.vague_category == "khu công nghiệp"
    d = legacy_analysis("so sánh top 2", has_rooms=True, hitl_pending=False, has_history=True)
    assert d.intent == "room_followup" and d.referenced_room_rank == 2
    e = legacy_analysis("giữ nguyên", has_rooms=True, hitl_pending=True, has_history=True)
    assert e.intent == "hitl_choice" and e.hitl_action is HitlAction.KEEP
