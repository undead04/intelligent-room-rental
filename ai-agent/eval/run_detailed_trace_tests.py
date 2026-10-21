"""Script kiểm thử chi tiết 7 kịch bản (Live Data) với Observability Tracing sâu từng lượt gọi Model & Tool.

Mục đích:
1. Bóc tách và hiển thị nhật ký (Event Logs) của TỪNG LẦN GỌI MODEL hoặc TOOL trong mỗi lượt chat.
2. Trả lời câu hỏi: Model được gọi mấy lần trong 1 turn? Có bị gọi lặp lại 2-3 lần cho cùng 1 tác vụ không?
3. Phân tích nguyên nhân Timeout (nếu có) và đo đạc độ trễ của từng công đoạn.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.routes import service
from core.memory import memory_manager
from core.schemas import AgentResponse


def print_turn_trace(turn_idx: int, user_query: str, res: AgentResponse, elapsed_total: float, trace_events: list[dict[str, Any]]):
    print("\n" + "-" * 75)
    print(f"💬 [LƯỢT {turn_idx}] User: \"{user_query}\"")
    print(f"⏱️ Tổng thời gian phản hồi: {elapsed_total:.2f}s")
    print("-" * 75)

    # 1. Thống kê số lần gọi Model & Tool
    model_reqs = [e for e in trace_events if e.get("type") == "model_request"]
    model_resps = [e for e in trace_events if e.get("type") == "model_response"]
    model_errors = [e for e in trace_events if e.get("type") == "model_error"]
    tool_starts = [e for e in trace_events if e.get("type") == "tool_started"]
    tool_ends = [e for e in trace_events if e.get("type") == "tool_finished"]

    print(f"📊 BẢNG TỔNG HỢP SỰ KIỆN (EVENT BREAKDOWN):")
    print(f"   • Số lần gọi Model: {len(model_reqs)} lần (Thành công: {len(model_resps)}, Lỗi/Timeout: {len(model_errors)})")
    print(f"   • Số lần gọi Tool : {len(tool_starts)} lần (Thành công: {len([t for t in tool_ends if t.get('status') == 'ok'])})")

    # 2. Chi tiết từng sự kiện theo trình tự thời gian
    print("\n📜 NHẬT KÝ CHI TIẾT TỪNG SỰ KIỆN (CHRONOLOGICAL EVENT LOG):")
    for idx, ev in enumerate(trace_events, 1):
        ev_type = ev.get("type")
        if ev_type == "model_request":
            call_idx = ev.get("model_call_index", "?")
            msgs = ev.get("message_count", 0)
            tools_cnt = ev.get("tool_count", 0)
            print(f"   [{idx}] 🤖 [MODEL CALL #{call_idx} START] Gửi {msgs} messages | Trang bị {tools_cnt} tools")
        elif ev_type == "model_response":
            ms = ev.get("elapsed_ms", 0)
            req_tools = ev.get("requested_tools") or []
            tools_info = f" -> Yêu cầu gọi tool: {req_tools}" if req_tools else " -> Trả về văn bản"
            print(f"   [{idx}] ✅ [MODEL CALL FINISH] Thời gian: {ms/1000:.2f}s{tools_info}")
        elif ev_type == "model_error":
            ms = ev.get("elapsed_ms", 0)
            err = ev.get("error", "")
            print(f"   [{idx}] ⚠️ [MODEL CALL TIMEOUT/ERROR] Thời gian: {ms/1000:.2f}s | Lỗi: {err[:150]}")
        elif ev_type == "tool_started":
            t_name = ev.get("tool_name", "tool")
            args = json.dumps(ev.get("arguments", {}), ensure_ascii=False)
            print(f"   [{idx}] 🛠️ [TOOL START] `{t_name}` với tham số: {args[:160]}...")
        elif ev_type == "tool_finished":
            t_name = ev.get("tool_name", "tool")
            ms = ev.get("elapsed_ms", 0)
            status = ev.get("status", "ok")
            res_summary = json.dumps(ev.get("result", {}), ensure_ascii=False)
            print(f"   [{idx}] 🏁 [TOOL END] `{t_name}` ({status.upper()}) trong {ms}ms | Kết quả: {res_summary[:160]}...")

    # 3. Đánh giá tính trùng lặp / lặp lại
    print("\n🔍 PHÂN TÍCH HÀNH VI GỌI MODEL & TOOL:")
    if len(model_reqs) == 0:
        print("   ℹ️ Lượt này KHÔNG gọi Model (xử lý bằng Guardrail Regex / Clarification Heuristic). Chi phí: 0 token, 0ms latency.")
    elif len(model_reqs) == 1:
        print("   ℹ️ Lượt này gọi Model đúng 1 LẦN duy nhất (NLU Structured Parsing hoặc Direct Response). Hoàn toàn tối ưu.")
    elif len(model_reqs) == 2:
        print("   ℹ️ Lượt này gọi Model 2 LẦN với 2 nhiệm vụ RIÊNG BIỆT:")
        print("      - Lần 1: Bóc tách nhu cầu (NLU Intent & Preferences) ở Preference Node.")
        print("      - Lần 2: Tư vấn phân tích đánh giá phòng (Decision ReAct) ở Decision Node.")
        print("      👉 Đây là phân tầng hợp lý của kiến trúc Agentic (không phải lặp lại vô nghĩa).")
    elif len(model_reqs) >= 3:
        print(f"   ⚠️ Lượt này gọi Model {len(model_reqs)} lần. Nguyên nhân có thể do:")
        print("      - Model gọi Tool giữa chừng (ReAct Multi-step).")
        print("      - Hoặc bị Timeout từ trước nên LangChain retry lại cùng 1 request.")

    # 4. Trích xuất câu trả lời và state
    print(f"\n🤖 Phản hồi của Bot:\n\"{res.text_reply[:250]}...\"")
    print(f"🏠 Số phòng trả về: {len(res.rooms)}")
    if res.current_preferences:
        p = res.current_preferences
        price_str = f"{p.max_price:,.0f}đ" if p.max_price is not None else "Chưa rõ"
        print(f"🎯 State: loc={p.location_text}, price={price_str}, rt={p.room_type}, amenities={p.amenities}")


def run_scenario(name: str, session_id: str, turns: list[str]):
    print("\n" + "=" * 80)
    print(f" 🔥 KỊCH BẢN: {name.upper()} (Session ID: `{session_id}`)")
    print("=" * 80)
    memory_manager.clear_session(session_id)

    for idx, q in enumerate(turns, 1):
        t0 = time.time()
        res = service.run(user_message=q, session_id=session_id)
        elapsed = time.time() - t0
        trace_events = getattr(res, "trace_events", []) or []
        print_turn_trace(idx, q, res, elapsed, trace_events)


if __name__ == "__main__":
    print("🚀 BẮT ĐẦU CHẠY PHÂN TÍCH OBSERVABILITY & EVENT LOGS CHO CÁC KỊCH BẢN THỰC...")

    # Kịch bản 1: Tiếng lóng, số tiền phức tạp & kế thừa đa lượt
    run_scenario(
        "Kịch bản 1: Tiếng lóng & Kế thừa đa lượt",
        "live-trace-tc1",
        [
            "Tìm cho mình căn studio loanh quanh 3 củ rưỡi ở Thủ Đức có máy lạnh với ban công nha",
            "Thế còn chỗ nào gần ĐH Bách Khoa không, bỏ ban công đi cũng được",
        ],
    )

    # Kịch bản 2: Phủ định khắt khe
    run_scenario(
        "Kịch bản 2: Phủ định khắt khe (Negation Guard)",
        "live-trace-tc2",
        [
            "Tìm phòng trọ ở Bình Thạnh giá dưới 4 triệu, nhưng tuyệt đối không lấy ký túc xá hay sleepbox và không chung chủ nhé",
        ],
    )

    # Kịch bản 3: Danh từ chung mơ hồ
    run_scenario(
        "Kịch bản 3: Danh từ chung mơ hồ & Smart Clarification",
        "live-trace-tc3",
        [
            "Tìm phòng gần khu công nghiệp giúp mình",
        ],
    )

    # Kịch bản 4: Semantic Guardrail
    run_scenario(
        "Kịch bản 4: Semantic Guardrail chặn ngoài luồng",
        "live-trace-tc4",
        [
            "Chỉ mình công thức nấu bún bò Huế ngon đi",
            "Viết giúp mình đoạn code Python quick sort",
        ],
    )

    # Kịch bản 5: Market Gap & HITL
    run_scenario(
        "Kịch bản 5: Market Gap & HITL khi 0 phòng",
        "live-trace-tc5",
        [
            "Tìm căn hộ chung cư cao cấp ở Quận 1 giá 1.5 triệu",
        ],
    )

    # Kịch bản 6: Khách hàng siêu khó tính (Follow-up + Kỹ năng Pháp lý + Kế thừa State)
    run_scenario(
        "Kịch bản 6: Khách hàng siêu khó tính & Chuyển đổi ngữ cảnh",
        "live-trace-tc6",
        [
            "Tìm giúp mình căn hộ studio ở Quận 2 (nay là TP. Thủ Đức) tầm 7-8 triệu, có ban công với máy giặt riêng nha",
            "Thôi Quận 2 đắt quá, đổi sang tìm phòng trọ thường ở Bình Thạnh đi. Ngân sách hạ xuống dưới 4 triệu thôi nhé, nhưng nhớ là phải có gác lửng",
            "Cái phòng Top 1 ở đường D2 lúc nãy có cho nuôi mèo không bạn? Với lại nếu mình ở 2 người thì có bị tính thêm phí sinh hoạt gì không?",
            "À nhân tiện cho mình hỏi, chủ trọ đòi giữ cọc 2 tháng và bắt ký hợp đồng 1 năm, nếu mình ở có 6 tháng muốn chuyển đi thì có đòi lại được tiền cọc không?",
        ],
    )

    # Kịch bản 7: Ngân sách không tưởng & HITL Broaden
    run_scenario(
        "Kịch bản 7: Ngân sách không tưởng & Nút mở rộng bán kính",
        "live-trace-tc7",
        [
            "Tìm giúp mình phòng studio cao cấp hoặc căn hộ đầy đủ máy lạnh, thang máy, giờ tự do ở Quận 1 mà giá dưới 2 triệu nha",
            "🧭 Mở rộng bán kính tìm kiếm lân cận",
        ],
    )

    print("\n🎉 HOÀN TẤT BÁO CÁO PHÂN TÍCH EVENT TRACING!")
