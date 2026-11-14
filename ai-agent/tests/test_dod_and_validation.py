"""Kiểm thử độc lập (Black-box) cho Trace Store cô lập, DoD Verifier và Validation 3 tầng phân cấp."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import MappingProxyType
from unittest.mock import MagicMock

import pytest

AI_AGENT_DIR = Path(__file__).resolve().parents[1]
if str(AI_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AI_AGENT_DIR))

from domain.enums import Amenity, RoomType
from domain.schemas import RoomItem, UserPreferenceState
from graph.builder import build_housing_graph, run_turn
from graph.deps import Deps
from graph.nodes.verify import make_verify_node
from graph.state import HousingAgentState
from graph.tracing import (
    TraceStore,
    bind_case_id,
    deep_freeze,
    emit_verifier_span,
    redact_sensitive_data,
    reset_case_id,
    tool_event,
    traced_call,
)
from safety.dod_verifier import derive_dod_spec, verify_dod
from safety.grounding import verify_answer_grounding


def _room(
    rid: str = "P101",
    rank: int = 1,
    price_vnd: float = 3_000_000,
    area_m2: float = 22.0,
    room_type: RoomType = RoomType.ROOM,
    bedrooms: int | None = 1,
    lat: float | None = 10.8700,
    lng: float | None = 106.8030,
    distance: str = "500 m",
    concept_scores: dict[str, float] | None = None,
) -> RoomItem:
    return RoomItem(
        id=rid,
        rank=rank,
        title=f"Phòng {rid} sạch đẹp",
        price=f"{price_vnd / 1_000_000:g} triệu/tháng",
        priceNum=price_vnd,
        area_m2=area_m2,
        bedrooms=bedrooms,
        room_type=room_type,
        address="Linh Trung, Thủ Đức",
        distance=distance,
        lat=lat,
        lng=lng,
        concept_scores=concept_scores or {},
    )


def _ok_search_span(query: str = "phòng trọ Thủ Đức") -> dict:
    return {
        "type": "tool_finished",
        "tool": "search_rooms",
        "tool_name": "search_rooms",
        "status": "ok",
        "args": {"query": query},
    }


# ===========================================================================
# 1) NHÓM KIỂM THỬ TRACE CÔ LẬP, JSONL, UNTRUNCATED & REDACTION
# ===========================================================================

def test_trace_events_removed_from_mutable_graph_state():
    """Trace tuyệt đối không được lưu trong HousingAgentState để tránh Agent chỉnh sửa."""
    assert "trace_events" not in HousingAgentState.__annotations__


def test_trace_store_jsonl_monotonic_versions_case_id_and_untruncated(tmp_path: Path):
    """Kiểm đủ trường JSONL: run_id, seq tăng đều, ts, type, args/result không cắt, versions, case_id."""
    store = TraceStore(
        run_id="run_test_01",
        versions={"prompt": "v2.1", "skill": "v1.4", "model": "gpt-4o-mini"},
        persist=True,
        persist_path=tmp_path / "run.jsonl",
    )
    tok = bind_case_id("eval_case_007")
    try:
        long_query = "tìm phòng trọ " + ("A" * 900)
        long_result = {"items": ["X" * 1200], "count": 1}
        state_box = {"resolved_lat": None}

        def _mutating_tool():
            state_box["resolved_lat"] = 10.87
            return long_result

        out = tool_event(
            store.sink(),
            "resolve_location",
            {"query": long_query},
            _mutating_tool,
            node="retrieval_node",
            state_before=lambda: dict(state_box),
            state_after=lambda: dict(state_box),
        )
        assert out == long_result

        class _FakeResp:
            content = "Kết quả mẫu"
            usage_metadata = {"input_tokens": 120, "output_tokens": 35}

        traced_call(
            store.sink(),
            lambda: _FakeResp(),
            node="decision_node",
            input_data={"prompt": "Hãy tóm tắt phòng P101"},
        )
        emit_verifier_span(
            store.sink(),
            verifier_output={"passed": True, "failures": []},
            next_decision="pass",
            node="verify_node",
        )
    finally:
        reset_case_id(tok)

    raw_lines = (tmp_path / "run.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(raw_lines) == 5  # tool_started, tool_finished, model_request, model_response, verifier_decision
    parsed = [json.loads(line) for line in raw_lines]

    seqs = [sp["seq"] for sp in parsed]
    assert seqs == [1, 2, 3, 4, 5]
    assert all(sp["run_id"] == "run_test_01" for sp in parsed)
    assert all(sp["case_id"] == "eval_case_007" for sp in parsed)
    assert all(sp["versions"] == {"prompt": "v2.1", "skill": "v1.4", "model": "gpt-4o-mini"} for sp in parsed)
    assert all(isinstance(sp["ts"], float) and sp["ts"] > 0 for sp in parsed)

    tool_fin = parsed[1]
    assert tool_fin["type"] == "tool_finished"
    assert len(tool_fin["args"]["query"]) > 900
    assert len(tool_fin["result"]["items"][0]) == 1200
    assert tool_fin["state_before"] == {"resolved_lat": None}
    assert tool_fin["state_after"] == {"resolved_lat": 10.87}
    assert isinstance(tool_fin["duration_ms"], int)

    model_resp = parsed[3]
    assert model_resp["type"] == "model_response"
    assert model_resp["input"] == {"prompt": "Hãy tóm tắt phòng P101"}
    assert model_resp["output"] == "Kết quả mẫu"
    assert model_resp["tokens_in"] == 120
    assert model_resp["tokens_out"] == 35
    assert isinstance(model_resp["duration_ms"], int)

    v_span = parsed[4]
    assert v_span["type"] == "verifier_decision"
    assert v_span["verifier_output"] == {"passed": True, "failures": []}
    assert v_span["next_decision"] == "pass"


def test_trace_redacts_api_keys_and_pii_and_is_tamper_proof():
    """Che khóa API & PII (SĐT, email, CCCD); bản chụp đóng băng không cho phép agent sửa."""
    raw = {
        "api_key": "sk-proj-abc1234567890XYZ",
        "gemini": "AIzaSyD-SecretKey1234567890",
        "text": "Liên hệ 0901234567 hoặc chu_tro@example.com, CCCD 079099001234",
        "authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
    }
    redacted = redact_sensitive_data(raw)
    dumped = json.dumps(redacted, ensure_ascii=False)
    assert "sk-proj-" not in dumped
    assert "AIzaSy" not in dumped
    assert "0901234567" not in dumped
    assert "chu_tro@example.com" not in dumped
    assert "079099001234" not in dumped
    assert "eyJhbGciOi" not in dumped

    store = TraceStore()
    store.append({"type": "tool_finished", "tool": "search_rooms", "status": "ok", "args": {"query": "q1"}})
    frozen = store.frozen_snapshot()
    assert isinstance(frozen, tuple)
    with pytest.raises(TypeError):
        frozen[0]["status"] = "hacked"  # type: ignore[index]


# ===========================================================================
# 2) NHÓM KIỂM THỬ CHỐNG GIAN LẬN (ANTI-TAMPERING) & FULL PASS/FAIL CẶP ĐÔI DoD
# ===========================================================================

def test_dod_spec_and_report_immutable_and_ignores_fake_agent_success():
    """Agent không thể sửa DoD/Report; lời tự báo 'Đã đặt thành công' khi 0 phòng vẫn FAIL."""
    spec = derive_dod_spec("new_search", UserPreferenceState(max_price=3_500_000), user_message="Tìm phòng dưới 3.5tr")
    with pytest.raises(Exception):
        spec.intent = "chitchat"  # type: ignore[misc]
    with pytest.raises(Exception):
        spec.conditions[0].threshold = 99_000_000  # type: ignore[misc]

    # Không có phòng nhưng Agent tự báo thành công
    report = verify_dod(
        spec,
        candidate_answer="Tuyệt vời! Đã đặt phòng thành công cho bạn với đầy đủ nội thất.",
        direct_system_state={"rooms": []},
        trace_spans=[_ok_search_span()],
    )
    out = report.to_verifier_output()
    assert out["passed"] is False
    cids = {f["condition_id"] for f in out["failures"]}
    assert "cond_factual_grounding" in cids

    with pytest.raises(Exception):
        report.passed = True  # type: ignore[misc]

    # Xác nhận freeze dict trực tiếp hoạt động
    frozen_dict = deep_freeze({"passed": False})
    assert isinstance(frozen_dict, MappingProxyType)
    with pytest.raises(TypeError):
        frozen_dict["passed"] = True  # type: ignore[index]


@pytest.mark.parametrize(
    "case_name,intent,pref_kwargs,matched_skill,user_msg,ok_rooms,ok_answer,ok_trace,ok_state_extra,bad_rooms,bad_answer,bad_trace,bad_state_extra,expected_fail_cid",
    [
        (
            "cond_search_trace",
            "new_search",
            {},
            None,
            "Tìm phòng trọ Thủ Đức",
            [_room()],
            "Phòng P101 giá 3 triệu/tháng, diện tích 22 m2 ở Thủ Đức.",
            [_ok_search_span()],
            {},
            [],
            "Phòng P101 giá 3 triệu/tháng.",
            [],  # Thiếu span search_rooms
            {},
            "cond_search_trace",
        ),
        (
            "cond_skill_trace",
            "skill_advice",
            {},
            "rental-contract-advisor",
            "Kinh nghiệm kiểm tra hợp đồng thuê trọ",
            [],
            "Bạn nên kiểm tra kỹ điều khoản tiền cọc, thời hạn báo trước và hợp đồng thuê trọ.",
            [{"type": "tool_finished", "tool": "consult_housing_skill", "status": "ok", "args": {"skill_name": "rental-contract-advisor"}}],
            {},
            [],
            "Bạn nên kiểm tra kỹ hợp đồng thuê trọ.",
            [],  # Không gọi consult_housing_skill
            {},
            "cond_skill_trace",
        ),
        (
            "cond_max_price",
            "chitchat",
            {"max_price": 3_000_000},
            None,
            "Tìm phòng giá rẻ",
            [_room(price_vnd=3_000_000)],
            "Phòng P101 giá 3 triệu/tháng.",
            [],
            {},
            [_room(price_vnd=4_500_000)],
            "Phòng P101 giá 4.5 triệu/tháng.",
            [],
            {},
            "cond_max_price",
        ),
        (
            "cond_min_price",
            "chitchat",
            {"min_price": 2_500_000},
            None,
            "Tìm phòng từ 2.5tr",
            [_room(price_vnd=3_000_000)],
            "Phòng P101 giá 3 triệu/tháng.",
            [],
            {},
            [_room(price_vnd=1_800_000)],
            "Phòng P101 giá 1.8 triệu/tháng.",
            [],
            {},
            "cond_min_price",
        ),
        (
            "cond_min_area",
            "chitchat",
            {"min_area": 20.0},
            None,
            "Tìm phòng rộng từ 20m2",
            [_room(area_m2=24.0)],
            "Phòng P101 rộng 24 m2, giá 3 triệu/tháng.",
            [],
            {},
            [_room(area_m2=14.0)],
            "Phòng P101 rộng 14 m2, giá 3 triệu/tháng.",
            [],
            {},
            "cond_min_area",
        ),
        (
            "cond_max_area",
            "chitchat",
            {"max_area": 30.0},
            None,
            "Tìm phòng tối đa 30m2",
            [_room(area_m2=25.0)],
            "Phòng P101 rộng 25 m2, giá 3 triệu/tháng.",
            [],
            {},
            [_room(area_m2=45.0)],
            "Phòng P101 rộng 45 m2, giá 3 triệu/tháng.",
            [],
            {},
            "cond_max_area",
        ),
        (
            "cond_min_bedrooms",
            "chitchat",
            {"min_bedrooms": 2},
            None,
            "Tìm căn hộ 2 phòng ngủ",
            [_room(bedrooms=2)],
            "Phòng P101 có 2 phòng ngủ, giá 3 triệu/tháng.",
            [],
            {},
            [_room(bedrooms=1)],
            "Phòng P101 có 1 phòng ngủ, giá 3 triệu/tháng.",
            [],
            {},
            "cond_min_bedrooms",
        ),
        (
            "cond_max_distance",
            "chitchat",
            {"lat": 10.8700, "lng": 106.8030, "max_distance_km": 2.0},
            None,
            "Tìm phòng gần điểm hẹn",
            [_room(lat=10.8710, lng=106.8040)],
            "Phòng P101 giá 3 triệu/tháng, gần điểm mốc.",
            [],
            {},
            [_room(lat=10.7500, lng=106.6600)],  # > 15 km
            "Phòng P101 giá 3 triệu/tháng, gần điểm mốc.",
            [],
            {},
            "cond_max_distance",
        ),
        (
            "cond_allowed_room_types",
            "chitchat",
            {"allowed_room_types": [RoomType.STUDIO]},
            None,
            "Tìm phòng studio",
            [_room(room_type=RoomType.STUDIO)],
            "Phòng P101 dạng studio giá 3 triệu/tháng.",
            [],
            {},
            [_room(room_type=RoomType.ROOM)],
            "Phòng P101 giá 3 triệu/tháng.",
            [],
            {},
            "cond_allowed_room_types",
        ),
        (
            "cond_excluded_room_types",
            "chitchat",
            {"excluded_room_types": [RoomType.SLEEPBOX]},
            None,
            "Không ở sleepbox",
            [_room(room_type=RoomType.ROOM)],
            "Phòng P101 là phòng trọ riêng, giá 3 triệu/tháng.",
            [],
            {},
            [_room(room_type=RoomType.SLEEPBOX)],
            "Phòng P101 giá 3 triệu/tháng.",
            [],
            {},
            "cond_excluded_room_types",
        ),
        (
            "cond_amenities",
            "chitchat",
            {"amenities": [Amenity.AIRCON]},
            None,
            "Tìm phòng có điều hòa",
            [_room(concept_scores={"aircon": 0.9})],
            "Phòng P101 có máy lạnh điều hòa, giá 3 triệu/tháng.",
            [],
            {},
            [_room(concept_scores={"aircon": 0.1})],
            "Phòng P101 có máy lạnh điều hòa, giá 3 triệu/tháng.",
            [],
            {},
            "cond_amenities",
        ),
        (
            "cond_factual_grounding",
            "chitchat",
            {},
            None,
            "Xem thông tin phòng",
            [_room(price_vnd=3_000_000)],
            "Phòng P101 giá 3 triệu/tháng.",
            [],
            {},
            [_room(price_vnd=3_000_000)],
            "Phòng P999 giá 1.5 triệu/tháng siêu rẻ.",  # Bịa ID & giá
            [],
            {},
            "cond_factual_grounding",
        ),
        (
            "cond_answer_relevance",
            "chitchat",
            {},
            None,
            "Phòng này giá bao nhiêu và có nuôi thú cưng không?",
            [_room(price_vnd=3_000_000)],
            "Phòng P101 có giá 3 triệu/tháng và cho phép nuôi thú cưng bình thường.",
            [],
            {},
            [_room(price_vnd=3_000_000)],
            "Khu vực này rất nhộn nhịp vào buổi tối.",  # Lạc đề, thiếu giá & thú cưng
            [],
            {},
            "cond_answer_relevance",
        ),
    ],
)
def test_every_dod_condition_has_pass_and_fail_synthetic_case(
    case_name,
    intent,
    pref_kwargs,
    matched_skill,
    user_msg,
    ok_rooms,
    ok_answer,
    ok_trace,
    ok_state_extra,
    bad_rooms,
    bad_answer,
    bad_trace,
    bad_state_extra,
    expected_fail_cid,
):
    """Mỗi điều kiện DoD đều phải có ít nhất 1 case ĐẠT và 1 case SAI trên dữ liệu tự dựng."""
    pref = UserPreferenceState(**pref_kwargs)
    spec = derive_dod_spec(intent, pref, user_message=user_msg, matched_skill=matched_skill)

    # Case ĐẠT
    pass_report = verify_dod(
        spec,
        candidate_answer=ok_answer,
        direct_system_state={"rooms": ok_rooms, **ok_state_extra},
        trace_spans=ok_trace,
        preferences=pref,
        enforce_trace=True,
    )
    pass_out = pass_report.to_verifier_output()
    assert pass_out["passed"] is True, f"[{case_name}] kỳ vọng PASS nhưng lỗi: {pass_out['failures']}"
    assert pass_out["failures"] == []

    # Case SAI
    fail_report = verify_dod(
        spec,
        candidate_answer=bad_answer,
        direct_system_state={"rooms": bad_rooms, **bad_state_extra},
        trace_spans=bad_trace,
        preferences=pref,
        enforce_trace=True,
    )
    fail_out = fail_report.to_verifier_output()
    assert fail_out["passed"] is False, f"[{case_name}] kỳ vọng FAIL nhưng lại PASS"
    fail_cids = {f["condition_id"] for f in fail_out["failures"]}
    assert expected_fail_cid in fail_cids, f"[{case_name}] thiếu mã điều kiện {expected_fail_cid} trong {fail_out['failures']}"
    for failure in fail_out["failures"]:
        assert {"condition_id", "actual", "expected"}.issubset(failure.keys())


def test_dod_special_requirements_mapped_to_human_and_missing_concept_marked_unverifiable():
    """Tiêu chí định tính tự do chuyển sang human review; thiếu concept_scores ghi rõ unverifiable_reason."""
    pref = UserPreferenceState(
        amenities=[Amenity.PET_ALLOWED],
        special_requirements=["hẻm yên tĩnh ít xe"],
    )
    spec = derive_dod_spec("chitchat", pref, user_message="Tìm phòng yên tĩnh cho nuôi mèo")
    cids = {c.condition_id: c for c in spec.conditions}
    assert cids["cond_special_requirements"].verifier_type == "human"
    assert cids["cond_special_requirements"].unverifiable_reason

    # Phòng không có concept_scores (mock tối giản) -> cond_amenities unverifiable (passed=None) thay vì tự bịa đạt
    report = verify_dod(
        spec,
        candidate_answer="Phòng P101 giá 3 triệu/tháng, cho nuôi thú cưng và yên tĩnh.",
        direct_system_state={"rooms": [_room(concept_scores={})]},
        trace_spans=[],
        preferences=pref,
    )
    unv_cids = {c.condition_id: c for c in report.unverifiable_conditions}
    assert "cond_amenities" in unv_cids
    assert unv_cids["cond_amenities"].unverifiable_reason
    assert "cond_special_requirements" in unv_cids


# ===========================================================================
# 3) NHÓM KIỂM THỬ VALIDATION 3 TẦNG SHORT-CIRCUIT & BOUNDED RETRY
# ===========================================================================

def test_validation_short_circuits_by_increasing_cost_and_returns_structured_errors():
    """Tầng 1 (hình dạng) lỗi -> dừng ở Tầng 1; Tầng 2 (nghiệp vụ) lỗi -> dừng ở Tầng 2; đủ trường/giá trị/mong đợi."""
    rooms = [
        _room("P101", rank=1, price_vnd=3_000_000, area_m2=22.0),
        _room("P102", rank=2, price_vnd=5_000_000, area_m2=35.0),
    ]

    # Tầng 1 lỗi (bảng Markdown) dù có kèm mã phòng ảo giác P999 (Tầng 3) -> DỪNG ở schema_format
    bad_t1 = "| Phòng | Giá |\n| --- | --- |\n| Phòng P999 | 1.2 triệu |"
    r1 = verify_answer_grounding(bad_t1, rooms, enforce_room_constraints=True, short_circuit=True)
    assert not r1.is_grounded
    assert r1.failed_tier == "schema_format"
    assert r1.checked == 0  # Tầng 3 chưa chạy
    assert r1.validation_errors[0].field == "answer_text.format"
    assert "Trường sai:" in r1.issues[0] and "Nhận được:" in r1.issues[0] and "Mong đợi:" in r1.issues[0]

    # Tầng 1 sạch, Tầng 2 lỗi (ràng buộc phòng + tráo giá Top 1 thành 5 triệu) + Tầng 3 (P999) -> DỪNG ở business_rule
    pref = UserPreferenceState(max_price=4_000_000)
    bad_t2 = "- Top 1 (P101) có giá 5 triệu/tháng rất tốt.\n- Ngoài ra còn phòng P999 giá 1.1 triệu/tháng."
    r2 = verify_answer_grounding(bad_t2, rooms, pref, enforce_room_constraints=True, short_circuit=True)
    assert not r2.is_grounded
    assert r2.failed_tier == "business_rule"
    assert r2.checked == 0  # Tầng 3 chưa chạy vì dừng ở Tầng 2
    assert any(e.tier == "business_rule" and e.actual_value for e in r2.validation_errors)

    # Tầng 1 & 2 sạch, Tầng 3 lỗi (đề cập số tiền bịa)
    bad_t3 = "- Phòng P101 (Top 1) có giá 3 triệu/tháng, phụ thu dọn phòng 950k/tháng."
    r3 = verify_answer_grounding(bad_t3, [rooms[0]], UserPreferenceState(max_price=4_000_000), enforce_room_constraints=True, short_circuit=True)
    assert not r3.is_grounded
    assert r3.failed_tier == "external_cross_check"
    assert r3.validation_errors[0].field == "answer_text.price_vnd"
    assert "950k" in str(r3.validation_errors[0].actual_value)


def _make_test_deps(*, trace_store: TraceStore, fast_llm: Any = None, enable_critic: bool = False) -> Deps:
    from core.session_store import SessionStore
    from tests.test_location_service import FakeDB

    return Deps(
        sessions=SessionStore(),
        get_llm=lambda role: fast_llm,
        base_prompt="BASE",
        decision_system_prompt="DECISION",
        search_rooms=lambda args: {"ok": True, "data": []},
        geocode=lambda q, h: None,
        admin_lookup=FakeDB(),
        consult_skill=lambda s, q: {"ok": False},
        skills=lambda: {},
        enable_critic=enable_critic,
        verify_answers=True,
        max_answer_retries=2,
        trace_store=trace_store,
    )


def test_verify_node_skips_critic_on_early_tier_fail_and_records_verifier_span():
    """Tầng 1/2/3 không đạt -> verify_node bỏ qua LLM Critic (tiết kiệm chi phí) & ghi span verifier_decision."""
    fast_llm = MagicMock()
    trace_store = TraceStore()
    deps = _make_test_deps(trace_store=trace_store, fast_llm=fast_llm, enable_critic=True)
    verify_node = make_verify_node(deps)

    res = verify_node({
        "user_message": "Tìm phòng trọ",
        "intent": "chitchat",
        "final_text": "| Phòng | Giá |\n| --- | --- |\n| P101 | 3 triệu |",
        "retrieved_rooms": [_room("P101", price_vnd=3_000_000)],
        "answer_retry_count": 0,
    })
    assert fast_llm.with_structured_output.call_count == 0 and fast_llm.invoke.call_count == 0
    assert res["answer_grounded"] is False
    assert res["verifier_decision"] == "retry"
    assert res["verifier_result"]["passed"] is False
    assert res["grounding_report"]["failed_tier"] == "schema_format"

    spans = trace_store.snapshot()
    assert len(spans) == 1
    assert spans[0]["type"] == "verifier_decision"
    assert spans[0]["passed"] is False
    assert spans[0]["next_decision"] == "retry"
    assert spans[0]["failed_tier"] == "schema_format"


def test_verify_node_bounded_retries_and_deterministic_fallback_and_stop_and_report():
    """Vượt max_answer_retries -> fallback_template cho cả regular và follow-up; lỗi trace/0 phòng -> stop_and_report."""
    trace_store = TraceStore()
    deps = _make_test_deps(trace_store=trace_store, enable_critic=False)
    verify_node = make_verify_node(deps)
    rooms = [_room("P101", price_vnd=3_000_000)]

    # Vượt giới hạn tự sửa ở chế độ follow-up -> PHẢI thay thế text ảo giác bằng fallback an toàn (không gửi lời sai)
    out_followup = verify_node({
        "user_message": "Phòng này nuôi mèo được không?",
        "intent": "chitchat",
        "is_followup": True,
        "focus_rank": 1,
        "final_text": "Phòng P999 giá 1.5 triệu/tháng cho nuôi thoải mái!",
        "retrieved_rooms": rooms,
        "answer_retry_count": 2,
    })
    assert out_followup["answer_grounded"] is True
    assert out_followup["verifier_decision"] == "fallback_template"
    assert out_followup["grounding_report"]["fallback_template_used"] is True
    assert "P999" not in out_followup["final_text"]
    assert "P101" in out_followup["final_text"] or "3" in out_followup["final_text"]

    # Trạng thái thực tế 0 phòng + thiếu trace search_rooms + Agent tự báo 'Đã đặt thành công' -> stop_and_report
    out_stop = verify_node({
        "user_message": "Tìm phòng Thủ Đức",
        "intent": "new_search",
        "final_text": "Đã đặt phòng thành công cho bạn!",
        "retrieved_rooms": [],
        "answer_retry_count": 0,
    })
    assert out_stop["answer_grounded"] is True
    assert out_stop["verifier_decision"] == "stop_and_report"
    assert out_stop["verifier_result"]["passed"] is False
    assert "Đã đặt phòng thành công" not in out_stop["final_text"]

    v_spans = [sp for sp in trace_store.snapshot() if sp["type"] == "verifier_decision"]
    assert len(v_spans) == 2
    assert [sp["next_decision"] for sp in v_spans] == ["fallback_template", "stop_and_report"]


def test_run_turn_captures_isolated_trace_store_without_state_leak():
    """Chạy đồ thị thực tế qua run_turn: trace được TraceStore ghi riêng kèm verifier_decision & case_id."""
    from intelligence.nlu import Priorities
    from tests.e2e_helpers import GOOD_ADVICE, FakeLLM, Harness, nlu, raw_room

    llm = (
        FakeLLM()
        .on(
            "TurnAnalysis",
            nlu(
                "new_search",
                priorities=Priorities(location="high"),
                location_text="UIT",
                location_kind="place",
                max_price=3_500_000,
                amenities_add=["ml"],
            ),
        )
        .on("Advice", GOOD_ADVICE)
    )
    rooms = [raw_room(1, 2_400_000, 25), raw_room(2, 2_800_000, 21), raw_room(3, 3_000_000, 30)]
    h = Harness(llm, rooms)
    store = TraceStore(session_id="s_e2e")
    resp = run_turn(
        h.graph,
        "tìm phòng gần UIT dưới 3tr5 có máy lạnh",
        session_id="s_e2e",
        case_id="case_e2e_01",
        trace_store=store,
    )
    assert resp.searched is True
    assert len(resp.rooms) == 3
    assert resp.grounding_report is not None
    assert resp.grounding_report.verifier_output is not None
    assert resp.grounding_report.verifier_output["passed"] is True

    spans = store.snapshot()
    assert len(spans) == len(resp.trace_events)
    assert all(sp["case_id"] == "case_e2e_01" for sp in spans)
    assert [sp["seq"] for sp in spans] == list(range(1, len(spans) + 1))
    assert any(sp["type"] == "tool_finished" and sp["tool"] == "search_rooms" for sp in spans)
    assert any(sp["type"] == "verifier_decision" and sp["next_decision"] == "pass" for sp in spans)
