import pytest
from domain.schemas import RoomItem
from eval.answer_relevance import (
    RELEVANCE_CASES,
    RelevanceJudgeReport,
    evaluate_answer_relevance,
)
from graph.deps import Deps, default_deps
from graph.nodes.verify import make_verify_node
from safety.grounding import (
    CriticVerificationReport,
    critic_answer_validation,
)
from tests.helpers import FakeModel
from tests.test_grounding import R


# ==============================================================================
# 1. TEST CRITIC ANSWER VALIDATION (ONLINE RUNTIME GUARDRAIL)
# ==============================================================================

def test_critic_answer_validation_structured_output():
    report = CriticVerificationReport(
        unsupported_claims=["Phòng 1 view biển", " "],
        unaddressed_questions=["Chưa trả lời về quy định thú cưng", " "],
    )
    m = FakeModel(report)
    res = critic_answer_validation(
        m,
        "Phòng nhatot_1 view biển",
        [R(1)],
        user_text="Phòng này có cho nuôi mèo không bạn?",
    )
    assert res.unsupported_claims == ["Phòng 1 view biển"]
    assert res.unaddressed_questions == ["Chưa trả lời về quy định thú cưng"]

    human = m.structured.calls[0][1][1]
    assert "<rooms_data>" in human
    assert "<user_query>\nPhòng này có cho nuôi mèo không bạn?\n</user_query>" in human
    assert "<answer>\nPhòng nhatot_1 view biển\n</answer>" in human


def test_critic_answer_validation_dict_and_fallback_models():
    # Model trả về dict
    dict_model = FakeModel({
        "unsupported_claims": ["claim1"],
        "unaddressed_questions": ["q1"],
    })
    res_dict = critic_answer_validation(dict_model, "answer", [R(1)])
    assert res_dict.unsupported_claims == ["claim1"]
    assert res_dict.unaddressed_questions == ["q1"]

    # Model trả về Exception -> không raise, trả report rỗng
    err_model = FakeModel(RuntimeError("API quota exceeded"))
    res_err = critic_answer_validation(err_model, "answer", [R(1)])
    assert res_err.unsupported_claims == []
    assert res_err.unaddressed_questions == []

    # Model là None hoặc answer rỗng -> trả rỗng
    assert critic_answer_validation(None, "answer", [R(1)]).unsupported_claims == []
    assert critic_answer_validation(dict_model, "   ", [R(1)]).unsupported_claims == []


# ==============================================================================
# 2. TEST EVALUATE ANSWER RELEVANCE (OFFLINE EVALUATION METRIC)
# ==============================================================================

def test_evaluate_answer_relevance_offline_cases():
    """Kiểm tra toàn bộ bộ ca benchmark chuẩn hoá khi chạy ở chế độ rule-based."""
    for case in RELEVANCE_CASES:
        rep = evaluate_answer_relevance(None, case.user_query, case.answer)
        if case.expected_relevant:
            assert rep.score >= 0.7, f"Ca đạt nhưng điểm thấp: {case.description} (score={rep.score})"
            assert not rep.unaddressed_aspects
        else:
            assert rep.score <= 0.4, f"Ca lạc đề nhưng điểm cao: {case.description} (score={rep.score})"
            assert rep.unaddressed_aspects


def test_evaluate_answer_relevance_llm_judge():
    judge_out = RelevanceJudgeReport(
        score=0.95,
        unaddressed_aspects=[],
        reason="Câu trả lời giải đáp chi tiết tất cả các câu hỏi của người dùng.",
    )
    m = FakeModel(judge_out)
    rep = evaluate_answer_relevance(m, "Hỏi về giá và thú cưng", "Trả lời đầy đủ")
    assert rep.score == 0.95
    assert not rep.unaddressed_aspects

    human = m.structured.calls[0][1][1]
    assert "<user_query>\nHỏi về giá và thú cưng\n</user_query>" in human
    assert "<answer>\nTrả lời đầy đủ\n</answer>" in human


def test_evaluate_answer_relevance_llm_judge_error_falls_back():
    err_model = FakeModel(RuntimeError("LLM call failed"))
    # Fallback về rule-based judge
    rep = evaluate_answer_relevance(
        err_model,
        "Phòng này có cho nuôi thú cưng không và cọc mấy tháng?",
        "Phòng cho phép nuôi mèo và cọc 1 tháng tiền phòng.",
    )
    assert rep.score >= 0.8
    assert not rep.unaddressed_aspects


# ==============================================================================
# 3. TEST VERIFY NODE INTEGRATION (SELF-RAG RETRY LOOP)
# ==============================================================================

def test_verify_node_triggers_retry_on_unaddressed_questions():
    critic_report = CriticVerificationReport(
        unsupported_claims=[],
        unaddressed_questions=["Người dùng hỏi về thú cưng nhưng câu trả lời chưa đề cập."],
    )
    critic_model = FakeModel(critic_report)

    deps = default_deps(enable_critic=True)
    deps.verify_answers = True
    deps.get_llm = lambda name: critic_model
    verify_node = make_verify_node(deps)

    room = RoomItem(id="nhatot_1", title="Phòng 1", price="3 triệu", priceNum=3_000_000, area="20m2", address="Q1", images=[], rank=1)
    state = {
        "final_text": "Phòng nhatot_1 có giá 3 triệu.",
        "retrieved_rooms": [room],
        "user_message": "Phòng nhatot_1 có cho nuôi thú cưng không?",
        "answer_retry_count": 0,
        "retry_notes": [],
    }

    result = verify_node(state)
    assert result["answer_grounded"] is False
    assert result["answer_retry_count"] == 1
    assert "Chưa trả lời đúng trọng tâm" in result["retry_notes"][0]
    assert "Chưa trả lời đúng trọng tâm câu hỏi của người dùng: Người dùng hỏi về thú cưng nhưng câu trả lời chưa đề cập." in result["answer_issues"]
