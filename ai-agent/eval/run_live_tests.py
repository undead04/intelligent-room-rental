"""Script chạy kiểm thử trực tiếp (LIVE INTEGRATION TEST) với Backend FastAPI và Local LLM thực tế.
Không sử dụng mock, gửi truy vấn thực và in kết quả chi tiết từng kịch bản.
"""

from __future__ import annotations

import json
import os
import sys
import time

# Thiết lập UTF-8 output cho console Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Thêm đường dẫn ai-agent vào sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.routes import service
from core.memory import memory_manager
from core.schemas import AgentResponse


def print_separator(title: str):
    print("\n" + "=" * 80)
    print(f" 🔥 {title.upper()}")
    print("=" * 80)


def run_live_test_case_1():
    print_separator("Test Case 1 (LIVE): Tiếng lóng, Số tiền phức tạp & Kế thừa đa lượt")
    session_id = "live-test-case-1"
    memory_manager.clear_session(session_id)

    # Turn 1
    q1 = "Tìm cho mình căn studio loanh quanh 3 củ rưỡi ở Thủ Đức có máy lạnh với ban công nha"
    print(f"\n[Turn 1] User: {q1}")
    t0 = time.time()
    res1: AgentResponse = service.run(user_message=q1, session_id=session_id)
    print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
    print(f"🤖 Bot reply:\n{res1.text_reply}\n")
    print(f"📊 Phòng tìm thấy: {len(res1.rooms)}")
    if res1.current_preferences:
        p = res1.current_preferences
        print(f"🎯 State sau Turn 1: room_type={p.room_type}, max_price={p.max_price:,.0f}đ, amenities={p.amenities}, location={p.location_text} (district_id={p.district_id})")

    # Turn 2
    q2 = "Thế còn chỗ nào gần ĐH Bách Khoa không, bỏ ban công đi cũng được"
    print(f"\n[Turn 2] User: {q2}")
    t0 = time.time()
    res2: AgentResponse = service.run(user_message=q2, session_id=session_id)
    print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
    print(f"🤖 Bot reply:\n{res2.text_reply}\n")
    print(f"📊 Phòng tìm thấy: {len(res2.rooms)}")
    if res2.current_preferences:
        p = res2.current_preferences
        print(f"🎯 State sau Turn 2: room_type={p.room_type}, max_price={p.max_price:,.0f}đ, amenities={p.amenities}, location={p.location_text} (lat={p.lat}, lng={p.lng})")


def run_live_test_case_2():
    print_separator("Test Case 2 (LIVE): Xử lý Phủ định khắt khe (Negation Guard)")
    session_id = "live-test-case-2"
    memory_manager.clear_session(session_id)

    q = "Tìm phòng trọ ở Bình Thạnh giá dưới 4 triệu, nhưng tuyệt đối không lấy ký túc xá hay sleepbox và không chung chủ nhé"
    print(f"\nUser: {q}")
    t0 = time.time()
    res: AgentResponse = service.run(user_message=q, session_id=session_id)
    print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
    print(f"🤖 Bot reply:\n{res.text_reply}\n")
    print(f"📊 Phòng tìm thấy: {len(res.rooms)}")
    if res.current_preferences:
        p = res.current_preferences
        print(f"🎯 State trích xuất: room_type={p.room_type} (không phải SLEEPBOX), max_price={p.max_price:,.0f}đ, amenities={p.amenities}")


def run_live_test_case_3():
    print_separator("Test Case 3 (LIVE): Danh từ chung mơ hồ & Smart Clarification")
    session_id = "live-test-case-3"
    memory_manager.clear_session(session_id)

    q = "Tìm phòng gần khu công nghiệp giúp mình"
    print(f"\nUser: {q}")
    t0 = time.time()
    res: AgentResponse = service.run(user_message=q, session_id=session_id)
    print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
    print(f"🤖 Bot reply (Clarification):\n{res.text_reply}\n")
    print(f"❓ Cần làm rõ: {res.need_clarification}")
    print(f"💡 Quick reply suggestions: {res.follow_up_questions}")


def run_live_test_case_4():
    print_separator("Test Case 4 (LIVE): Semantic Guardrail (Off-Topic Chặn linh hoạt)")
    session_id = "live-test-case-4"

    queries = [
        "Chỉ mình công thức nấu bún bò Huế ngon đi",
        "Viết giúp mình đoạn code Python quick sort",
    ]
    for q in queries:
        print(f"\nUser: {q}")
        t0 = time.time()
        res: AgentResponse = service.run(user_message=q, session_id=session_id)
        print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
        print(f"🤖 Bot reply (Polite Refusal):\n{res.text_reply}")
        print(f"🛡️ Guardrail report: {res.grounding_report}")


def run_live_test_case_5():
    print_separator("Test Case 5 (LIVE): Xử lý Market Gap & Human-in-the-Loop khi 0 phòng")
    session_id = "live-test-case-5"
    memory_manager.clear_session(session_id)

    q = "Tìm căn hộ chung cư cao cấp ở Quận 1 giá 1.5 triệu"
    print(f"\nUser: {q}")
    t0 = time.time()
    res: AgentResponse = service.run(user_message=q, session_id=session_id)
    print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
    print(f"🤖 Bot reply:\n{res.text_reply}\n")
    if res.hitl_proposal:
        hitl = res.hitl_proposal
        print("📋 Khối đề xuất HITL Proposal kiểu Claude UI:")
        print(f"   - Thông điệp phân tích thị trường: {hitl.message}")
        print(f"   - Giá sàn ghi nhận: {hitl.market_min_price_str}")
        print(f"   - Ngân sách đề xuất: {hitl.proposed_budget_str}")
        print("   - Các lựa chọn tương tác:")
        for opt in hitl.options:
            print(f"     + [{opt.id}] {opt.action_text}")


def run_live_test_case_6():
    print_separator("Test Case 6 (LIVE): Khách hàng siêu khó tính (5 Turns trong session-hardcore-test-2026)")
    session_id = "session-hardcore-test-2026"
    memory_manager.clear_session(session_id)

    turns = [
        "Tìm giúp mình căn hộ studio ở Quận 2 (nay là TP. Thủ Đức) tầm 7-8 triệu, có ban công với máy giặt riêng nha",
        "Thôi Quận 2 đắt quá, đổi sang tìm phòng trọ thường ở Bình Thạnh đi. Ngân sách hạ xuống dưới 4 triệu thôi nhé, nhưng nhớ là phải có gác lửng",
        "Cái phòng Top 1 ở đường D2 lúc nãy có cho nuôi mèo không bạn? Với lại nếu mình ở 2 người thì có bị tính thêm phí sinh hoạt gì không?",
        "À nhân tiện cho mình hỏi, chủ trọ đòi giữ cọc 2 tháng và bắt ký hợp đồng 1 năm, nếu mình ở có 6 tháng muốn chuyển đi thì có đòi lại được tiền cọc không?",
        "Thôi nghe phức tạp quá, bây giờ quay lại tìm phòng trọ ở Bình Thạnh dưới 4 triệu có gác lúc nãy đi, nhưng đổi ý là phải được nuôi pet nha",
    ]

    for idx, q in enumerate(turns, 1):
        print(f"\n--- [Turn {idx}/5] User: {q} ---")
        t0 = time.time()
        res: AgentResponse = service.run(user_message=q, session_id=session_id)
        print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
        print(f"🤖 Bot reply:\n{res.text_reply[:350]}...\n")
        if res.current_preferences and (res.current_preferences.location_text or res.current_preferences.max_price):
            p = res.current_preferences
            print(f"🎯 State hiện tại: loc={p.location_text}, price={p.max_price:,.0f}đ, rt={p.room_type}, amenities={p.amenities}")
        print(f"🏠 Phòng tìm được: {len(res.rooms)}")


def run_live_test_case_7():
    print_separator("Test Case 7 (LIVE): Ngân sách không tưởng & HITL Broaden (session-hitl-hardcore-2026)")
    session_id = "session-hitl-hardcore-2026"
    memory_manager.clear_session(session_id)

    # Turn 1
    q1 = "Tìm giúp mình phòng studio cao cấp hoặc căn hộ đầy đủ máy lạnh, thang máy, giờ tự do ở Quận 1 mà giá dưới 2 triệu nha"
    print(f"\n[Turn 1] User: {q1}")
    t0 = time.time()
    res1: AgentResponse = service.run(user_message=q1, session_id=session_id)
    print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
    print(f"🤖 Bot reply:\n{res1.text_reply[:300]}...\n")
    print(f"📋 HITL Proposal is_market_gap: {res1.hitl_proposal.is_market_gap if res1.hitl_proposal else False}")

    # Turn 2: Bấm nút mở rộng bán kính
    q2 = "🧭 Mở rộng bán kính tìm kiếm lân cận"
    print(f"\n[Turn 2] User chọn: {q2}")
    t0 = time.time()
    res2: AgentResponse = service.run(user_message=q2, session_id=session_id)
    print(f"⏱️ Thời gian phản hồi: {time.time() - t0:.2f}s")
    print(f"🤖 Bot reply:\n{res2.text_reply[:400]}...\n")
    print(f"🏠 Số phòng tìm được sau khi mở rộng: {len(res2.rooms)}")
    if res2.insights:
        print(f"🏆 Lý do chọn Top 1: {res2.insights.top_1_reason}")


if __name__ == "__main__":
    print("🚀 BẮT ĐẦU CHẠY KIỂM THỬ LIVE TOÀN DIỆN VỚI BACKEND & LOCAL LLM...")
    test_cases = [
        ("Test Case 1", run_live_test_case_1),
        ("Test Case 2", run_live_test_case_2),
        ("Test Case 3", run_live_test_case_3),
        ("Test Case 4", run_live_test_case_4),
        ("Test Case 5", run_live_test_case_5),
        ("Test Case 6", run_live_test_case_6),
        ("Test Case 7", run_live_test_case_7),
    ]

    results = {}
    for name, fn in test_cases:
        try:
            fn()
            results[name] = "PASSED ✅"
        except Exception as e:
            print(f"\n❌ Lỗi khi chạy {name}: {e}")
            import traceback
            traceback.print_exc()
            results[name] = f"FAILED ❌ ({e})"

    print("\n" + "=" * 80)
    print("📊 BẢNG TỔNG KẾT LIVE TESTS:")
    for name, status in results.items():
        print(f"  • {name}: {status}")
    print("=" * 80)
