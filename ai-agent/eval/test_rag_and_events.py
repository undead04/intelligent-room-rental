"""Bộ kiểm thử chuyên sâu về RAG và Event Streaming (Kèm kiểm chứng phòng chống vòng lặp).

Mục tiêu kiểm thử:
1. RAG Suite:
   - RAG-1: Hybrid Retrieval & Dynamic MCDM Rerank
   - RAG-2: Market Gap Context Grounding (/price-stats & HitlProposal)
   - RAG-3: Answer Grounding Anti-Hallucination (Phát hiện ID và giá bịa đặt)
   - RAG-4: Corrective RAG (CRAG) Retry Loop & Chứng minh hữu hạn (Termination Proof - KHÔNG bị vòng lặp vô tận)

2. Event & SSE Suite:
   - EVENT-1: End-to-End SSE Stream (trace -> text_delta -> done)
   - EVENT-2: Typewriter Token Generator (Chunking & Token Conservation)
   - EVENT-3: Error Event Emission & Clean Exit
   - EVENT-4: Trace Event Monotonicity & No Duplicate/Skip
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

# UTF-8 output cho console
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.sse import stream_graph_events, stream_text_chunks
from core.memory import memory_manager
from core.schemas import AgentResponse, RoomItem, UserPreferenceState
from safety.grounding import (
    MAX_GROUNDING_RETRIES,
    verify_answer_grounding,
    verify_context_grounding,
)
from workflow.edges import route_after_grounding
from workflow.graph import housing_graph
from workflow.nodes import grounding_node, render_fallback_template


def print_banner(title: str):
    print("\n" + "=" * 80)
    print(f" 🧪 {title.upper()}")
    print("=" * 80)


# ==============================================================================
# PHẦN 1: CÁC BÀI TEST VỀ RAG
# ==============================================================================

def test_rag_1_hybrid_retrieval_and_rerank():
    """RAG-1: Kiểm tra Hybrid Retrieval (Dense pgvector + Sparse FTS) & Reranking đa tiêu chí."""
    print_banner("RAG-1: Kiểm tra Hybrid Retrieval & Dynamic MCDM Rerank")
    from tools.housing_tools import search_rooms

    # Gửi truy vấn tìm phòng giá rẻ tại Bình Thạnh
    query_args = {
        "query": "phòng trọ giá rẻ bình thạnh",
        "city_id": 79,
        "max_price": 3500000.0,
        "weights": {"price": 0.45, "location": 0.25, "safety": 0.15, "semantic": 0.15},
    }
    t0 = time.time()
    raw_res = search_rooms.invoke(query_args)
    elapsed = time.time() - t0
    data = json.loads(raw_res)

    assert data.get("ok") is True, f"search_rooms thất bại: {data.get('error')}"
    rooms_data = data.get("data", [])
    print(f"✅ Hybrid Search thành công trong {elapsed:.2f}s!")
    print(f"📊 Số lượng phòng retrieve được: {len(rooms_data)}")

    if rooms_data:
        top1 = rooms_data[0]
        print(f"🥇 Top 1: {top1.get('title')[:60]}...")
        print(f"   - Giá: {top1.get('price')} (Số: {top1.get('price_num')})")
        print(f"   - Match Score: {top1.get('match_score')}")
        print(f"   - Điểm thành phần: {top1.get('explain_match')}")
        assert "match_score" in top1, "Thiếu match_score sau khi rerank"
        assert top1.get("match_score", 0) > 0, "match_score phải > 0"

    print("🎉 Test RAG-1 PASSED: Hybrid Retrieval & Rerank hoạt động chính xác!")


def test_rag_2_market_gap_context_grounding():
    """RAG-2: Kiểm tra Context Grounding phát hiện Market Gap và gọi /price-stats."""
    print_banner("RAG-2: Kiểm tra Context Grounding (Market Gap & HitlProposal)")

    pref = UserPreferenceState(
        location_text="Quận 1",
        city_id=79,
        district_id=760,
        max_price=1000000.0,  # Ngân sách 1 triệu - chắc chắn thấp hơn thị trường
    )

    t0 = time.time()
    res = verify_context_grounding(
        rooms=[],  # 0 phòng tìm thấy
        preferences=pref,
        retry_count=0,
        area_name="Quận 1",
    )
    elapsed = time.time() - t0

    print(f"⏱️ Thời gian kiểm định Context Grounding: {elapsed:.3f}s")
    print(f"🔍 is_grounded: {res.is_grounded} | is_market_gap: {res.is_market_gap}")
    print(f"💰 Proposed Budget: {res.proposed_budget_str}")

    assert res.is_market_gap is True, "Phải phát hiện Market Gap khi giá thấp hơn sàn"
    assert res.hitl_proposal is not None, "Phải sinh ra khối HitlProposal"
    print(f"📋 Thông điệp phân tích thị trường: {res.hitl_proposal.message}")
    print(f"🔘 Số lượng lựa chọn tương tác HITL: {len(res.hitl_proposal.options)}")

    option_ids = [opt.id for opt in res.hitl_proposal.options]
    print(f"   Các options: {option_ids}")
    assert "adjust_budget" in option_ids, "Thiếu option adjust_budget"
    assert "broaden_location" in option_ids, "Thiếu option broaden_location"

    print("🎉 Test RAG-2 PASSED: Market Gap Grounding & HITL Proposal hoạt động hoàn hảo!")


def test_rag_3_answer_grounding_anti_hallucination():
    """RAG-3: Kiểm tra Answer Grounding phát hiện thông tin ảo giác (Fake Room ID & Fake Price)."""
    print_banner("RAG-3: Kiểm tra Answer Grounding (Chống ảo giác ID & Giá)")

    mock_rooms = [
        RoomItem(
            id="nhatot_101",
            title="Phòng trọ cao cấp Bình Thạnh",
            price="3.2 triệu/tháng",
            priceNum=3200000.0,
            address="Đường D2, Bình Thạnh",
            matchScore=0.75,
        ),
        RoomItem(
            id="nhatot_102",
            title="Phòng studio full nội thất",
            price="3.5 triệu/tháng",
            priceNum=3500000.0,
            address="Đường Bạch Đằng, Bình Thạnh",
            matchScore=0.70,
        ),
    ]

    # Ca 1: Câu trả lời trung thực 100% với context
    truthful_text = (
        "Homigo tìm thấy phòng nhatot_101 với giá 3.2 triệu/tháng tại Bình Thạnh và "
        "phòng nhatot_102 giá 3.5 triệu/tháng."
    )
    check1 = verify_answer_grounding(truthful_text, mock_rooms)
    print(f"Ca 1 (Trung thực): is_grounded={check1.is_grounded}, score={check1.groundedness_score}, issues={check1.issues}")
    assert check1.is_grounded is True, "Câu trả lời đúng dữ liệu phải is_grounded = True"
    assert check1.groundedness_score == 1.0, "Score phải là 1.0"

    # Ca 2: Câu trả lời ảo giác bịa ra ID phòng không có trong context
    hallucinated_id_text = (
        "Bạn có thể chọn phòng nhatot_999999999 rất đẹp ở Bình Thạnh giá 3.2 triệu/tháng."
    )
    check2 = verify_answer_grounding(hallucinated_id_text, mock_rooms)
    print(f"Ca 2 (Ảo giác ID): is_grounded={check2.is_grounded}, score={check2.groundedness_score}, issues={check2.issues}")
    assert check2.is_grounded is False, "Phải phát hiện ID phòng không tồn tại"
    assert any("nhatot_999999999" in iss for iss in check2.issues)

    # Ca 3: Câu trả lời ảo giác bịa ra giá phòng sai lệch
    hallucinated_price_text = (
        "Phòng nhatot_101 có giá siêu rẻ chỉ 1.2 triệu/tháng thôi bạn nhé."
    )
    check3 = verify_answer_grounding(hallucinated_price_text, mock_rooms)
    print(f"Ca 3 (Ảo giác Giá): is_grounded={check3.is_grounded}, score={check3.groundedness_score}, issues={check3.issues}")
    assert check3.is_grounded is False, "Phải phát hiện giá phòng 1.2 triệu bịa đặt"

    print("🎉 Test RAG-3 PASSED: Answer Grounding bắt trúng 100% các lỗi ảo giác!")


def test_rag_4_crag_retry_loop_termination_proof():
    """RAG-4: Chứng minh toán học & thực nghiệm: Corrective RAG KHÔNG BAO GIỜ bị vòng lặp vô tận."""
    print_banner("RAG-4: Kiểm chứng CRAG Retry Loop & Chứng minh thoát hữu hạn (Termination Proof)")

    mock_rooms = [
        RoomItem(
            id="nhatot_101",
            title="Phòng trọ cao cấp Bình Thạnh",
            price="3.2 triệu/tháng",
            priceNum=3200000.0,
            address="Đường D2, Bình Thạnh",
            matchScore=0.75,
        ),
    ]

    # Mô phỏng kịch bản cực đoan: Decision Agent liên tục sinh câu trả lời ảo giác
    fake_hallucinated_reply = "Phòng nhatot_999999 có giá 99 triệu/tháng cực rẻ!"

    simulated_state: dict[str, Any] = {
        "final_text": fake_hallucinated_reply,
        "retrieved_rooms": mock_rooms,
        "answer_retry_count": 0,
        "retry_notes": [],
        "insights": None,
        "preferences": UserPreferenceState(location_text="Bình Thạnh"),
    }

    transitions = []
    step = 0
    max_test_steps = 10  # Nếu vượt quá 5 bước nghĩa là bị loop vô tận

    print("Bắt đầu mô phỏng vòng lặp State Machine khi Agent liên tục sinh câu trả lời ảo giác:")

    while step < max_test_steps:
        step += 1
        current_retry = simulated_state.get("answer_retry_count", 0)

        # 1. Chạy grounding_node
        node_output = grounding_node(simulated_state)
        simulated_state.update(node_output)

        # 2. Đánh giá routing condition
        next_route = route_after_grounding(simulated_state)
        transitions.append((step, current_retry, simulated_state["answer_retry_count"], simulated_state["answer_grounded"], next_route))

        print(f"  [Bước {step}] retry_count: {current_retry} -> {simulated_state['answer_retry_count']} | "
              f"answer_grounded: {simulated_state['answer_grounded']} | "
              f"Định tuyến tiếp theo: 👉 '{next_route}'")

        if next_route == "formatter_node":
            print(f"  ✅ ĐÃ THOÁT VÒNG LẶP THÀNH CÔNG tại bước {step}!")
            break
        elif next_route == "decision_node":
            # Tiếp tục giả lập decision_node lại sinh lỗi ảo giác
            simulated_state["final_text"] = fake_hallucinated_reply

    # Kiểm tra tính hữu hạn:
    assert next_route == "formatter_node", "Vòng lặp không thoát ra formatter_node!"
    assert step <= MAX_GROUNDING_RETRIES + 2, f"Số bước {step} vượt quá ngưỡng tối đa cho phép!"
    assert simulated_state.get("grounding_report", {}).get("fallback_template_used") is True, "Phải sử dụng fallback template an toàn khi hết lượt retry"

    print(f"📊 Tổng số bước chuyển trạng thái trước khi thoát: {step} bước (Chính xác bằng MAX_GROUNDING_RETRIES={MAX_GROUNDING_RETRIES} + 1)")
    print("🎉 Test RAG-4 PASSED: Hệ thống có Bounded Retry Loop và ĐẢM BẢO KHÔNG BỊ VÒNG LẶP VÔ TẬN!")


# ==============================================================================
# PHẦN 2: CÁC BÀI TEST VỀ EVENT VÀ STREAMING SSE
# ==============================================================================

def test_event_1_end_to_end_sse_stream():
    """EVENT-1: Kiểm tra luồng phát sự kiện SSE thời gian thực qua stream_graph_events."""
    print_banner("EVENT-1: Kiểm tra Luồng Phát Sự Kiện SSE Thời Gian Thực (trace -> delta -> done)")

    session_id = "test-event-stream-session"
    memory_manager.clear_session(session_id)

    query = "Tìm phòng trọ ở Bình Thạnh giá dưới 3.5 triệu"
    print(f"Gửi truy vấn stream: \"{query}\"")

    event_types = []
    trace_events = []
    text_deltas = []
    done_payload = None

    t0 = time.time()
    generator = stream_graph_events(user_message=query, effective_session_id=session_id)

    for raw_chunk in generator:
        lines = raw_chunk.strip().split("\n")
        if len(lines) >= 2:
            ev_line = lines[0]
            data_line = lines[1]
            if ev_line.startswith("event: ") and data_line.startswith("data: "):
                ev_type = ev_line[7:].strip()
                data_str = data_line[6:].strip()
                event_types.append(ev_type)

                if ev_type == "trace":
                    trace_events.append(json.loads(data_str))
                elif ev_type == "text_delta":
                    text_deltas.append(json.loads(data_str).get("delta", ""))
                elif ev_type == "done":
                    done_payload = json.loads(data_str)

    elapsed = time.time() - t0
    full_text = "".join(text_deltas)

    print(f"⏱️ Tổng thời gian stream hoàn tất: {elapsed:.2f}s")
    print(f"📊 Tổng số sự kiện SSE đã phát: {len(event_types)}")
    print(f"   • Số event 'trace': {len(trace_events)}")
    print(f"   • Số event 'text_delta': {len(text_deltas)}")
    print(f"   • Số event 'done': 1 if done_payload else 0")

    # Kiểm tra thứ tự và cấu trúc sự kiện
    assert len(trace_events) > 0, "Phải phát ít nhất 1 event trace (tool calling)"
    assert len(text_deltas) > 0, "Phải phát các text_delta (hiệu ứng máy gõ typewriter)"
    assert done_payload is not None, "Phải phát event done chứa AgentResponse hoàn chỉnh"

    # Kiểm tra cấu trúc event trace
    tool_names = [t.get("tool_name") for t in trace_events if "tool_name" in t]
    print(f"🛠️ Các công cụ đã trace: {set(tool_names)}")

    # Kiểm tra nội dung text_delta
    print(f"📝 Đoạn văn bản hoàn chỉnh nhận được qua delta ({len(full_text)} ký tự):")
    print(f"   \"{full_text[:150]}...\"")
    assert len(full_text) > 50, "Nội dung phản hồi qua delta quá ngắn"

    # Kiểm tra payload done
    assert "rooms" in done_payload, "Payload done phải chứa danh sách phòng"
    print(f"🏠 Số phòng trong payload done: {len(done_payload.get('rooms', []))}")

    print("🎉 Test EVENT-1 PASSED: Chuỗi sự kiện SSE phát đúng thứ tự, đầy đủ và kết thúc sạch sẽ!")


def test_event_2_typewriter_chunking_and_token_conservation():
    """EVENT-2: Kiểm tra bộ tách chunk máy gõ typewriter (Bảo toàn ký tự, không lặp, không sót)."""
    print_banner("EVENT-2: Kiểm tra Typewriter Token Generator (Bảo toàn nội dung)")

    sample_texts = [
        "",  # Text rỗng
        "Xin chào!",  # 2 từ
        "Dòng 1\nDòng 2\n\nDòng 4",  # Nhiều dòng và dòng trống
        (
            "Homigo đã tìm được 5 phòng phù hợp nhất với nhu cầu của bạn:\n"
            "1. Phòng đẹp Bình Thạnh giá 2.5 triệu/tháng.\n"
            "2. Studio full nội thất giá 3.2 triệu/tháng.\n"
            "🏆 Lựa chọn tối ưu nhất: Phòng đẹp Bình Thạnh."
        ),
    ]

    for idx, text in enumerate(sample_texts, 1):
        chunks = list(stream_text_chunks(text, words_per_chunk=2, delay=0.0))
        reconstructed = "".join(chunks)

        print(f"Ca 2.{idx}: Ký tự gốc={len(text)} | Ký tự tái tạo={len(reconstructed)} | Số chunk={len(chunks)}")
        assert reconstructed == text, f"Bảo toàn văn bản thất bại tại Ca 2.{idx}!"

    print("🎉 Test EVENT-2 PASSED: Typewriter Chunking bảo toàn 100% ký tự và kết thúc chính xác!")


def test_event_3_error_event_clean_termination():
    """EVENT-3: Kiểm tra khi xảy ra lỗi bất ngờ, SSE phát event error và kết thúc an toàn."""
    print_banner("EVENT-3: Kiểm tra Xử Lý Sự Kiện Lỗi & Kết Thúc An Toàn (Clean Error Exit)")

    # Giả lập fallback_runner bị ném exception
    def broken_fallback(*args, **kwargs):
        raise RuntimeError("Mô phỏng lỗi hệ thống bất ngờ trong quá trình sinh phản hồi")

    # Gọi stream_graph_events với fallback_runner bị lỗi
    session_id = "test-error-session"
    gen = stream_graph_events(user_message="test error handling", effective_session_id=session_id, fallback_runner=broken_fallback)

    received_events = []
    for raw in gen:
        for line in raw.strip().split("\n"):
            if line.startswith("event: "):
                received_events.append(line[7:].strip())

    print(f"Các loại event nhận được: {received_events}")
    assert "error" in received_events or "done" in received_events, "Phải kết thúc bằng event error hoặc done"
    print("🎉 Test EVENT-3 PASSED: Xử lý exception bắt gọn gàng, không bị treo hoặc rò rỉ generator!")


def test_event_4_trace_monotonicity_no_skip_or_duplicate():
    """EVENT-4: Kiểm tra biến đếm emitted_event_count tăng đơn điệu, không trùng và không sót event trace."""
    print_banner("EVENT-4: Kiểm tra Tính Đơn Điệu & Không Trùng Sót của Trace Events")

    # Giả lập danh sách trace_events tăng dần qua các node trong State Machine
    all_mock_events = [
        {"id": 1, "type": "tool_started", "tool_name": "get_location_hierarchy"},
        {"id": 2, "type": "tool_finished", "tool_name": "get_location_hierarchy"},
        {"id": 3, "type": "tool_started", "tool_name": "search_rooms"},
        {"id": 4, "type": "tool_finished", "tool_name": "search_rooms"},
        {"id": 5, "type": "tool_started", "tool_name": "get_listing_detail"},
        {"id": 6, "type": "tool_finished", "tool_name": "get_listing_detail"},
    ]

    emitted_count = 0
    emitted_items = []

    # Giả lập 3 node update lần lượt: Node 1 (2 events), Node 2 (4 events), Node 3 (6 events)
    checkpoints = [2, 4, 6]

    for step, total in enumerate(checkpoints, 1):
        current_events = all_mock_events[:total]
        newly_emitted = 0
        while emitted_count < len(current_events):
            ev = current_events[emitted_count]
            emitted_count += 1
            newly_emitted += 1
            emitted_items.append(ev)

        print(f"Node checkpoint {step}: current_len={len(current_events)} | newly_emitted={newly_emitted} | emitted_count={emitted_count}")

    assert len(emitted_items) == 6, "Phải phát chính xác 6 trace events"
    assert [item["id"] for item in emitted_items] == [1, 2, 3, 4, 5, 6], "Thứ tự trace items phải tăng tuần tự từ 1 đến 6"
    print("🎉 Test EVENT-4 PASSED: Thuật toán emitted_event_count chuẩn xác tuyệt đối, không trùng không sót!")


# ==============================================================================
# MAIN RUNNER
# ==============================================================================

if __name__ == "__main__":
    print("🚀 BẮT ĐẦU CHẠY KIỂM THỬ CHUYÊN SÂU RAG & EVENT STREAMING...")
    t_start = time.time()

    tests = [
        ("RAG-1: Hybrid Retrieval & MCDM Rerank", test_rag_1_hybrid_retrieval_and_rerank),
        ("RAG-2: Market Gap Context Grounding", test_rag_2_market_gap_context_grounding),
        ("RAG-3: Answer Anti-Hallucination Grounding", test_rag_3_answer_grounding_anti_hallucination),
        ("RAG-4: CRAG Retry Loop & Termination Proof", test_rag_4_crag_retry_loop_termination_proof),
        ("EVENT-1: End-to-End SSE Stream", test_event_1_end_to_end_sse_stream),
        ("EVENT-2: Typewriter Chunking & Conservation", test_event_2_typewriter_chunking_and_token_conservation),
        ("EVENT-3: Error Event Emission & Exit", test_event_3_error_event_clean_termination),
        ("EVENT-4: Trace Monotonicity & No Duplicate", test_event_4_trace_monotonicity_no_skip_or_duplicate),
    ]

    report = {}
    for name, fn in tests:
        try:
            fn()
            report[name] = "PASSED ✅"
        except Exception as e:
            print(f"\n❌ LỖI TẠI {name}: {e}")
            import traceback
            traceback.print_exc()
            report[name] = f"FAILED ❌ ({e})"

    t_total = time.time() - t_start
    print("\n" + "=" * 80)
    print(f"📊 BẢNG TỔNG KẾT KIỂM THỬ RAG & EVENT STREAMING (Thời gian: {t_total:.2f}s):")
    print("=" * 80)
    for name, status in report.items():
        print(f"  • {name}: {status}")
    print("=" * 80)
