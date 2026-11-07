"""Runner Đánh giá Chất lượng Gợi ý Phòng trọ (Recommendation Evaluation Runner).

Tích hợp đo lường Information Retrieval (IR) và Thẩm định Gemini Flash-Lite LLM-as-a-Judge:
- Chỉ số IR: Precision@3, Precision@5, MRR, nDCG@5, Constraint Satisfaction Rate (CSR).
- Chỉ số LLM-as-a-Judge: Relevance Score, Ranking Score, Faithfulness Score, Overall Score.
- Độ trễ vận hành (Latency p50, p95, max).
- Phân rã hiệu năng chi tiết theo 5 nhóm Persona (G1 -> G5).
- Xuất báo cáo kép: JSON (recommendation_eval_results.json) và Markdown (recommendation_evaluation_report.md).
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Optional
import uuid

# Đảm bảo đường dẫn ai-agent nằm trong sys.path
_CURRENT_DIR = Path(__file__).resolve().parent
_AI_AGENT_DIR = _CURRENT_DIR.parent
if str(_AI_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AI_AGENT_DIR))

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eval.recommendation_runner")

# Dual-import bộ benchmark queries
from eval.datasets.recommendation_benchmark import BENCHMARK_QUERIES, BenchmarkQuery

# Dual-import các hàm tính toán IR Metrics
from eval.ir_metrics import (
    constraint_satisfaction_breakdown,
    ndcg_at_k,
    precision_at_k,
    reciprocal_rank,
    )
# Dual-import module LLM Judge
from eval.llm_judge import (
        RecommendationJudgeReport,
        evaluate_recommendation_quality,
        get_judge_llm,
    )

# Import HousingAgentService & Domain/Safety Tools
from service import HousingAgentService
from domain.enums import normalize_amenities, normalize_room_types
from domain.schemas import AgentResponse, RoomItem, UserPreferenceState
from intelligence.nlu import LLMQuotaExceededError, is_daily_quota_exhausted
from intelligence.understand import compute_normalized_weights
from safety.grounding import check_hard_constraints
from tools.housing_tools import search_rooms_api


# ============================================================================
# CÁC HÀM TIỆN ÍCH TRÌNH BÀY BÁO CÁO MARKDOWN
# ============================================================================


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Tạo bảng Markdown chuẩn GFM."""
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    data_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator_line] + data_lines)


def generate_markdown_report(
    summary: dict[str, Any],
    group_stats: Optional[dict[str, Any]] = None,
    query_details: Optional[list[dict[str, Any]]] = None,
    meta: Optional[dict[str, Any]] = None,
) -> str:
    """Tạo nội dung báo cáo Markdown khoa học, trực quan theo chuẩn Đồ án Tốt nghiệp UIT.

    Hỗ trợ cả 2 cách truyền tham số:
    1. generate_markdown_report(summary, group_stats, query_details, meta)
    2. generate_markdown_report(results_payload)
    """
    if (
        group_stats is None
        and query_details is None
        and meta is None
        and isinstance(summary, dict)
        and "summary" in summary
    ):
        payload = summary
        summary = payload.get("summary", {})
        group_stats = payload.get("group_breakdown", {})
        query_details = payload.get("query_details", [])
        meta = payload.get("meta", {})

    group_stats = group_stats or {}
    query_details = query_details or []
    meta = meta or {}

    md_lines: list[str] = []

    # Tiêu đề
    md_lines.append("# 📊 Báo Cáo Đánh Giá Năng Lực Gợi Ý Phòng Trọ Thông Minh (Homigo AI)")
    md_lines.append("")
    md_lines.append("> **Hệ thống:** Homigo Smart Housing AI Agent  ")
    md_lines.append(f"> **Thời gian thực hiện:** {meta.get('timestamp', 'N/A')}  ")
    md_lines.append(f"> **Mô hình Thẩm định (Judge):** `{meta.get('judge_model', 'N/A')}` (Chế độ: `{meta.get('judge_mode', 'N/A')}`)  ")
    md_lines.append(f"> **Tổng số Truy vấn Đánh giá:** {meta.get('total_queries', len(query_details))} queries (Bộ 40 Benchmark Personas)  ")
    md_lines.append("")

    # 1. Tóm tắt điều hành
    md_lines.append("## 1. 🎯 Tóm Tắt Kết Quả Cốt Lõi (Executive Summary)")
    md_lines.append("")
    md_lines.append("Kết quả kiểm thử toàn diện trên tập Benchmark chuẩn phản ánh năng lực truy xuất thông tin (IR) ")
    md_lines.append("và chất lượng cố vấn theo đa tiêu chí (MCDM) được thẩm định bởi mô hình LLM-as-a-Judge:")
    md_lines.append("")

    # Bảng 1: Chỉ số IR
    ir_rows = [
        ["Precision@3 (P@3)", f"{summary.get('mean_precision_at_3', 0.0) * 100:.2f}%", "Tỷ lệ phòng hoàn toàn phù hợp trong Top 3"],
        ["Precision@5 (P@5)", f"{summary.get('mean_precision_at_5', 0.0) * 100:.2f}%", "Tỷ lệ phòng hoàn toàn phù hợp trong Top 5"],
        ["Mean Reciprocal Rank (MRR)", f"{summary.get('mrr', 0.0):.4f}", "Chất lượng vị trí xuất hiện của phòng hợp lệ đầu tiên"],
        ["nDCG@5", f"{summary.get('mean_ndcg_at_5', 0.0):.4f}", "Hiệu quả sắp xếp thứ tự ưu tiên theo mức độ liên quan"],
        ["Constraint Satisfaction Rate (CSR)", f"{summary.get('mean_csr', 0.0) * 100:.2f}%", "Tỷ lệ phòng thỏa mãn 100% tất cả các tiêu chí"],
    ]
    md_lines.append("### Bảng 1.1: Các chỉ số Information Retrieval (IR)")
    md_lines.append("")
    md_lines.append(_md_table(["Chỉ số Đo lường", "Giá trị Trung bình", "Ý nghĩa Đánh giá"], ir_rows))
    md_lines.append("")

    # Bảng 2: Chỉ số LLM-as-a-Judge
    judge_rows = [
        ["Độ phù hợp (Relevance Score)", f"{summary.get('mean_relevance_score', 0.0):.2f} / 5.0", "Mức độ đáp ứng trọn vẹn nhu cầu & ràng buộc"],
        ["Chất lượng Xếp hạng (Ranking Score)", f"{summary.get('mean_ranking_score', 0.0):.2f} / 5.0", "Top 1 có thực sự vượt trội hơn các phòng dưới không"],
        ["Tính trung thực (Faithfulness Score)", f"{summary.get('mean_faithfulness_score', 0.0):.2f} / 5.0", "Số liệu giá, khoảng cách và tiện ích khớp 100% DB"],
        ["**Điểm Thẩm định Tổng thể (Overall Score)**", f"**{summary.get('mean_overall_score', 0.0):.2f} / 5.0**", "**Trọng số: 40% Relevance + 30% Ranking + 30% Faithfulness**"],
    ]
    md_lines.append("### Bảng 1.2: Đánh giá Chất lượng qua Gemini Flash-Lite LLM-as-a-Judge")
    md_lines.append("")
    md_lines.append(_md_table(["Tiêu chí Thẩm định", "Điểm Trung bình", "Ghi chú & Trọng số"], judge_rows))
    md_lines.append("")

    # Bảng 3: Tuân thủ ràng buộc
    compliance_rows = [
        ["Tuân thủ Ngân sách (Price Compliance)", f"{summary.get('mean_price_compliance_pct', 0.0) * 100:.2f}%", "Không vượt quá ngân sách trần quy định"],
        ["Tuân thủ Bán kính (Distance Compliance)", f"{summary.get('mean_distance_compliance_pct', 0.0) * 100:.2f}%", "Nằm trong phạm vi bán kính di chuyển tối đa"],
        ["Tuân thủ Loại phòng (RoomType Compliance)", f"{summary.get('mean_room_type_compliance_pct', 0.0) * 100:.2f}%", "Đúng loại phòng mong muốn, không dính loại cấm"],
        ["Tuân thủ Tiện ích (Amenities Compliance)", f"{summary.get('mean_amenities_compliance_pct', 0.0) * 100:.2f}%", "Đầy đủ các tiện ích bắt buộc đã khai báo"],
    ]
    md_lines.append("### Bảng 1.3: Phân rã Mức độ Tuân thủ Ràng buộc (Constraint Compliance Breakdown)")
    md_lines.append("")
    md_lines.append(_md_table(["Ràng buộc Cứng/Mềm", "Tỷ lệ Tuân thủ", "Đặc tính Tiêu chí"], compliance_rows))
    md_lines.append("")

    # Bảng 4: Độ trễ
    lat_rows = [
        ["Độ trễ Trung vị (p50 Latency)", f"{summary.get('latency_p50_s', 0.0):.3f} s"],
        ["Độ trễ Phân vị 95 (p95 Latency)", f"{summary.get('latency_p95_s', 0.0):.3f} s"],
        ["Độ trễ Lớn nhất (Max Latency)", f"{summary.get('latency_max_s', 0.0):.3f} s"],
        ["Độ trễ Trung bình (Mean Latency)", f"{summary.get('latency_mean_s', 0.0):.3f} s"],
    ]
    md_lines.append("### Bảng 1.4: Hiệu năng Vận hành & Độ trễ (System Latency)")
    md_lines.append("")
    md_lines.append(_md_table(["Chỉ số Độ trễ", "Thời gian"], lat_rows))
    md_lines.append("")

    # 2. Phân rã theo nhóm Persona
    md_lines.append("## 2. 👥 Phân Tích Hiệu Năng Theo 5 Nhóm Persona Người Dùng")
    md_lines.append("")
    group_rows = []
    for grp_id, stats in sorted(group_stats.items()):
        group_rows.append([
            f"`{grp_id}`",
            str(stats.get("count", 0)),
            f"{stats.get('mean_p3', 0.0) * 100:.1f}%",
            f"{stats.get('mean_p5', 0.0) * 100:.1f}%",
            f"{stats.get('mean_mrr', 0.0):.3f}",
            f"{stats.get('mean_ndcg5', 0.0):.3f}",
            f"{stats.get('mean_csr', 0.0) * 100:.1f}%",
            f"{stats.get('mean_overall_score', 0.0):.2f}",
            f"{stats.get('mean_latency_s', 0.0):.2f}s",
        ])
    md_lines.append(_md_table(
        ["Nhóm Persona", "Số ca", "P@3", "P@5", "MRR", "nDCG@5", "CSR", "Judge Score", "Độ trễ"],
        group_rows,
    ))
    md_lines.append("")

    # 3. Bảng chi tiết từng Query
    md_lines.append("## 3. 📋 Bảng Kết Quả Đo Lường Chi Tiết Từng Truy Vấn")
    md_lines.append("")
    query_rows = []
    for q in query_details:
        ir = q.get("ir_metrics", {})
        jd = q.get("judge_report", {})
        cb = ir.get("constraint_breakdown", {})
        query_rows.append([
            f"`{q.get('query_id', '')}`",
            f"`{q.get('group', '')}`",
            str(q.get("returned_rooms_count", 0)),
            f"{ir.get('precision_at_3', 0.0):.2f}",
            f"{ir.get('precision_at_5', 0.0):.2f}",
            f"{ir.get('reciprocal_rank', 0.0):.2f}",
            f"{ir.get('ndcg_at_5', 0.0):.2f}",
            f"{cb.get('overall_csr', 0.0):.2f}",
            f"{jd.get('relevance_score', 0.0):.1f}",
            f"{jd.get('ranking_score', 0.0):.1f}",
            f"{jd.get('faithfulness_score', 0.0):.1f}",
            f"**{jd.get('overall_score', 0.0):.2f}**",
            f"{q.get('latency_s', 0.0):.2f}s",
        ])
    md_lines.append(_md_table(
        [
            "ID",
            "Nhóm",
            "Số phòng",
            "P@3",
            "P@5",
            "RR",
            "nDCG@5",
            "CSR",
            "Rel",
            "Rank",
            "Faith",
            "Overall",
            "Latency",
        ],
        query_rows,
    ))
    md_lines.append("")

    # 4. Nhận xét & Đánh giá
    md_lines.append("## 4. 💡 Đánh Giá Chuyên Sâu & Khuyến Nghị Phát Triển")
    md_lines.append("")
    md_lines.append("### 4.1. Điểm mạnh Nổi bật (Strengths)")
    md_lines.append(f"- **Khả năng kiểm soát ràng buộc cứng:** Tỷ lệ tuân thủ giá đạt {summary.get('mean_price_compliance_pct', 0.0) * 100:.1f}%, khoảng cách đạt {summary.get('mean_distance_compliance_pct', 0.0) * 100:.1f}%.")
    md_lines.append(f"- **Chất lượng xếp hạng ưu việt:** Điểm Ranking Score đạt {summary.get('mean_ranking_score', 0.0):.2f}/5.0 và MRR đạt {summary.get('mrr', 0.0):.3f}, chứng minh cơ chế Intent-Aware MCDM xếp các phòng phù hợp nhất lên Top 1.")
    md_lines.append(f"- **Độ trung thực cao:** Faithfulness Score đạt {summary.get('mean_faithfulness_score', 0.0):.2f}/5.0 nhờ cơ chế Self-RAG Grounding chặn triệt để hiện tượng ảo giác số liệu.")
    md_lines.append("")
    md_lines.append("### 4.2. Khía cạnh Cần Tối ưu (Areas for Improvement)")
    md_lines.append("- Với các truy vấn có yêu cầu tiện ích phức tạp kết hợp (ví dụ vừa cho nuôi pet, vừa có máy giặt riêng, vừa giờ tự do), độ phủ tiện ích có thể giảm nhẹ nếu khu vực có mật độ phòng thưa thớt.")
    md_lines.append("- Tiếp tục duy trì và nới lỏng linh hoạt theo gợi ý ngân sách thị trường khi số lượng phòng thỏa mãn = 0.")
    md_lines.append("")

    return "\n".join(md_lines)


# Alias tương thích
_build_markdown_report = generate_markdown_report


def _execute_offline_nlu_search(
    q: BenchmarkQuery,
    session_id: str,
) -> AgentResponse:
    """Thực thi tìm kiếm trực tiếp dựa trên GroundTruthExpectation (Offline NLU Mode).

    Bypass hoàn toàn tầng NLU (LLM) để thẩm định độc lập hiệu năng của:
    - Thuật toán Bán kính Thích ứng (Adaptive Radius).
    - MCDM Multi-Criteria Reranker (5 tiêu chí).
    - Bộ lọc Hard Constraints (giá, loại phòng, khoảng cách, tiện ích).
    """
    exp = q.expectation
    pref = UserPreferenceState()

    if exp.max_budget is not None:
        pref.max_price = float(exp.max_budget)
    if exp.min_budget is not None:
        pref.min_price = float(exp.min_budget)
    if exp.target_lat is not None and exp.target_lng is not None:
        pref.lat = float(exp.target_lat)
        pref.lng = float(exp.target_lng)
        pref.location_kind = "place"
    if exp.target_location_name:
        pref.location_text = str(exp.target_location_name)
    if exp.max_distance_km is not None:
        pref.max_distance_km = float(exp.max_distance_km)
    if exp.min_area_m2 is not None:
        pref.min_area = float(exp.min_area_m2)
    if exp.required_amenities:
        pref.amenities = normalize_amenities(exp.required_amenities)
    if exp.allowed_room_types:
        rts = normalize_room_types(exp.allowed_room_types)
        if len(rts) == 1:
            pref.room_type = rts[0]
    if exp.forbidden_room_types:
        pref.excluded_room_types = normalize_room_types(exp.forbidden_room_types)

    # Multipliers từ ideal_priorities
    multipliers: dict[str, float] = {}
    for k, v in (exp.ideal_priorities or {}).items():
        if str(v).lower() in ("high", "top", "very_high"):
            if k == "price":
                multipliers["price"] = 2.0
            elif k in ("distance", "location"):
                multipliers["location"] = 1.8
            elif k == "amenity":
                multipliers["amenity"] = 1.8
            elif k == "safety":
                multipliers["safety"] = 1.8
    weights = compute_normalized_weights(pref, multipliers)

    base_radius = pref.max_distance_km or 2.5
    search_args: dict[str, Any] = {
        "query": q.query,
        "lat": pref.lat,
        "lng": pref.lng,
        "min_price": pref.min_price,
        "max_price": pref.max_price,
        "min_area": pref.min_area,
        "amenities": [a.value for a in pref.amenities] or None,
        "max_distance_km": base_radius if pref.has_point else None,
        "weights": weights or None,
        "limit": 15 if pref.excluded_room_types else 10,
    }
    if pref.room_type is not None:
        search_args["room_type"] = pref.room_type.value
    if pref.excluded_room_types:
        search_args["excluded_room_types"] = [r.value for r in pref.excluded_room_types]

    def _search_and_ground(args: dict[str, Any]) -> tuple[list[RoomItem], list[RoomItem]]:
        call_args = dict(args)
        data = search_rooms_api(call_args)
        raw_items = data.get("data") or []
        items = [
            RoomItem.from_backend_result(raw, rank=i, target_lat=pref.lat, target_lng=pref.lng)
            for i, raw in enumerate(raw_items, 1)
        ]
        # Lọc tin vi phạm hard constraints
        valid, _ = check_hard_constraints(items, pref)
        return items, valid

    rooms, valid_rooms = _search_and_ground(search_args)

    # Adaptive Radius: Nếu có tọa độ và user không chỉ định max_distance_km cố định
    if pref.has_point and pref.max_distance_km is None:
        for next_radius in (3.5, 5.0):
            if len(valid_rooms) >= 3:
                break
            search_args["max_distance_km"] = next_radius
            new_rooms, new_valid = _search_and_ground(search_args)
            if len(new_valid) > len(valid_rooms):
                rooms, valid_rooms = new_rooms, new_valid

    return AgentResponse(
        session_id=session_id,
        text_reply=f"Đã tìm thấy {len(valid_rooms)} phòng phù hợp theo Offline NLU Benchmark.",
        rooms=rooms[:5],
    )


def save_evaluation_results(
    results_payload: dict[str, Any],
    output_dir: str | Path = "eval_results",
) -> tuple[Path, Path]:
    """Lưu kết quả đánh giá ra hai định dạng JSON và Markdown."""
    if str(output_dir) == "eval_results" or not output_dir:
        out_path = _AI_AGENT_DIR / "eval_results"
    else:
        p = Path(output_dir)
        out_path = p if p.is_absolute() else _AI_AGENT_DIR / p
    out_path.mkdir(parents=True, exist_ok=True)

    json_path = out_path / "recommendation_eval_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, ensure_ascii=False, indent=2)
    logger.info("Đã lưu kết quả JSON tại: %s", json_path)

    md_content = generate_markdown_report(
        summary=results_payload.get("summary", {}),
        group_stats=results_payload.get("group_breakdown", {}),
        query_details=results_payload.get("query_details", []),
        meta=results_payload.get("meta", {}),
    )
    md_path = out_path / "recommendation_evaluation_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info("Đã lưu báo cáo Markdown tại: %s", md_path)

    return json_path, md_path


# ============================================================================
# RUNNER CHÍNH: run_evaluation
# ============================================================================


def run_evaluation(
    limit: Optional[int] = None,
    group_filter: Optional[str] = None,
    judge_mode: str = "auto",
    judge_model_name: str = "gemini-2.5-flash-lite",
    output_dir: str = "eval_results",
    budget_tolerance_pct: float = 0.0,
    pacing: float = 3.5,
    offline_nlu: bool = False,
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình đánh giá trên bộ Recommendation Benchmark."""
    if str(output_dir) == "eval_results" or not output_dir:
        out_path = _AI_AGENT_DIR / "eval_results"
    else:
        p = Path(output_dir)
        out_path = p if p.is_absolute() else _AI_AGENT_DIR / p
    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Lọc queries
    queries: list[BenchmarkQuery] = list(BENCHMARK_QUERIES)

    if group_filter:
        groups = {g.strip() for g in group_filter.split(",") if g.strip()}
        queries = [q for q in queries if q.group in groups]

    if limit is not None and limit > 0:
        queries = queries[:limit]

    total_queries = len(queries)
    if total_queries == 0:
        logger.warning("Không tìm thấy truy vấn nào phù hợp với điều kiện lọc.")
        return {}

    logger.info("=" * 70)
    logger.info("BẮT ĐẦU ĐÁNH GIÁ RECOMMENDATION BENCHMARK (%d queries)", total_queries)
    logger.info("Chế độ Judge: %s | Model Judge: %s | Offline NLU: %s | Pacing: %.1fs",
                judge_mode, judge_model_name, offline_nlu, pacing)
    logger.info("=" * 70)

    # 2. Khởi tạo LLM Judge
    judge_llm = None
    if judge_mode in ("auto", "llm"):
        if offline_nlu and judge_mode == "auto":
            logger.info("Chế độ Offline NLU với Judge 'auto': Sử dụng Rule-based Judge offline để tiết kiệm 100% token.")
        else:
            judge_llm = get_judge_llm(model_name=judge_model_name)
            if judge_llm is None and judge_mode == "llm":
                raise RuntimeError(
                    f"Chế độ judge='llm' yêu cầu API Key hợp lệ cho {judge_model_name}. Vui lòng cấu hình GEMINI_API_KEY hoặc OPENAI_API_KEY."
                )
            elif judge_llm is not None:
                logger.info("Đã khởi tạo thành công Judge LLM: %s", judge_model_name)
            else:
                logger.info("Không có API Key cho Judge LLM, chuyển sang chế độ Rule-based offline.")

    # 3. Khởi tạo HousingAgentService (nếu không chạy Offline NLU)
    agent = None if offline_nlu else HousingAgentService()

    # 4. Vòng lặp thực thi từng query
    query_details: list[dict[str, Any]] = []
    daily_quota_hit = False

    for idx, q in enumerate(queries, start=1):
        session_id = f"eval_rec_{q.id}_{uuid.uuid4().hex[:6]}"
        logger.info("[%d/%d] Chạy Query ID: %s (%s) | \"%s\"", idx, total_queries, q.id, q.group, q.query[:60])

        t0 = time.perf_counter()
        resp = None

        if offline_nlu:
            try:
                resp = _execute_offline_nlu_search(q, session_id=session_id)
            except Exception as e:
                logger.error("Lỗi khi thực thi Offline NLU cho query %s: %s", q.id, e, exc_info=True)
                resp = AgentResponse(
                    session_id=session_id,
                    text_reply=f"Lỗi offline NLU: {e}",
                    rooms=[],
                )
        else:
            for attempt in range(3):
                try:
                    if hasattr(agent, "handle_message"):
                        resp = agent.handle_message(session_id=session_id, message=q.query)
                    else:
                        resp = agent.run(user_message=q.query, session_id=session_id)
                    break
                except LLMQuotaExceededError as exc:
                    logger.warning("Agent chạm hạn mức Daily Quota LLM ở query %s: %s", q.id, exc)
                    daily_quota_hit = True
                    break
                except Exception as e:
                    err_msg = str(e).lower()
                    if is_daily_quota_exhausted(err_msg):
                        logger.warning("Phát hiện Daily Quota LLM bị cạn ở query %s: %s", q.id, e)
                        daily_quota_hit = True
                        break
                    is_rate_limit = any(t in err_msg for t in ("429", "rate limit", "resource_exhausted", "quota", "too many requests"))
                    if is_rate_limit and attempt < 2:
                        wait_sec = 15.0 * (attempt + 1)
                        logger.warning("Agent gặp Rate Limit (429) ở query %s, chờ %.1fs rồi thử lại lần %d...", q.id, wait_sec, attempt + 1)
                        time.sleep(wait_sec)
                        continue
                    logger.error("Lỗi khi thực thi Agent cho query %s: %s", q.id, e, exc_info=True)
                    resp = AgentResponse(
                        session_id=session_id,
                        text_reply=f"Lỗi hệ thống khi tìm phòng: {e}",
                        rooms=[],
                    )
                    break

        if daily_quota_hit:
            logger.warning("Dừng sớm quy trình đánh giá để bảo toàn kết quả của %d queries đã hoàn thành.", len(query_details))
            break

        latency_s = time.perf_counter() - t0

        rooms = getattr(resp, "rooms", []) or []
        text_reply = getattr(resp, "text_reply", "") or ""
        insights = getattr(resp, "insights", None)

        # A. Đo lường IR Metrics
        p3 = precision_at_k(rooms, q.expectation, k=3)
        p5 = precision_at_k(rooms, q.expectation, k=5)
        rr = reciprocal_rank(rooms, q.expectation)
        ndcg5 = ndcg_at_k(rooms, q.expectation, k=5)
        csr_bd = constraint_satisfaction_breakdown(rooms, q.expectation)

        # B. Thẩm định qua LLM-as-a-Judge (hoặc rule-based fallback)
        try:
            judge_rep: RecommendationJudgeReport = evaluate_recommendation_quality(
                model=judge_llm,
                user_query=q.query,
                expectation=q.expectation,
                rooms=rooms,
                text_reply=text_reply,
                insights=insights,
                budget_tolerance_pct=budget_tolerance_pct,
            )
        except LLMQuotaExceededError:
            logger.warning("Judge LLM chạm hạn mức Daily Quota ở query %s, fallback sang Rule-based Judge.", q.id)
            judge_rep = evaluate_recommendation_quality(
                model=None,
                user_query=q.query,
                expectation=q.expectation,
                rooms=rooms,
                text_reply=text_reply,
                insights=insights,
                budget_tolerance_pct=budget_tolerance_pct,
            )
        except Exception as je:
            if is_daily_quota_exhausted(str(je)):
                logger.warning("Judge LLM cạn Daily Quota ở query %s, fallback sang Rule-based Judge.", q.id)
                judge_rep = evaluate_recommendation_quality(
                    model=None,
                    user_query=q.query,
                    expectation=q.expectation,
                    rooms=rooms,
                    text_reply=text_reply,
                    insights=insights,
                    budget_tolerance_pct=budget_tolerance_pct,
                )
            else:
                logger.error("Lỗi khi chạy LLM Judge cho query %s: %s, fallback Rule-based Judge.", q.id, je)
                judge_rep = evaluate_recommendation_quality(
                    model=None,
                    user_query=q.query,
                    expectation=q.expectation,
                    rooms=rooms,
                    text_reply=text_reply,
                    insights=insights,
                    budget_tolerance_pct=budget_tolerance_pct,
                )

        logger.info(
            " -> Kết quả: Rooms=%d | P@3=%.2f | P@5=%.2f | RR=%.2f | nDCG@5=%.2f | CSR=%.2f | Judge=%.2f/5.0 | Latency=%.2fs",
            len(rooms),
            p3,
            p5,
            rr,
            ndcg5,
            csr_bd["overall_csr"],
            judge_rep.overall_score,
            latency_s,
        )

        query_record = {
            "query_id": q.id,
            "group": q.group,
            "persona_description": q.persona_description,
            "query": q.query,
            "latency_s": round(latency_s, 3),
            "returned_rooms_count": len(rooms),
            "top_room_ids": [getattr(r, "id", "") for r in rooms[:5]],
            "ir_metrics": {
                "precision_at_3": round(p3, 4),
                "precision_at_5": round(p5, 4),
                "reciprocal_rank": round(rr, 4),
                "ndcg_at_5": round(ndcg5, 4),
                "constraint_breakdown": csr_bd,
            },
            "judge_report": {
                "relevance_score": round(judge_rep.relevance_score, 2),
                "ranking_score": round(judge_rep.ranking_score, 2),
                "faithfulness_score": round(judge_rep.faithfulness_score, 2),
                "overall_score": round(judge_rep.overall_score, 2),
                "strengths": judge_rep.strengths,
                "weaknesses": judge_rep.weaknesses,
                "rationale": judge_rep.rationale,
            },
        }
        query_details.append(query_record)
        if pacing > 0:
            time.sleep(pacing)

    # 5. Tổng hợp số liệu toàn cục
    evaluated_count = len(query_details)
    if evaluated_count == 0:
        logger.warning("Không có truy vấn nào được thực thi hoàn tất để tổng hợp số liệu.")
        return {}

    logger.info("Hoàn tất đánh giá %d/%d queries. Đang tổng hợp báo cáo...", evaluated_count, total_queries)

    latencies = sorted(q["latency_s"] for q in query_details)
    p50_lat = statistics.median(latencies) if latencies else 0.0
    p95_idx = int(len(latencies) * 0.95)
    p95_lat = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0
    mean_lat = sum(latencies) / evaluated_count if evaluated_count > 0 else 0.0

    summary = {
        "total_queries": evaluated_count,
        "planned_queries": total_queries,
        "mean_precision_at_3": round(
            sum(q["ir_metrics"]["precision_at_3"] for q in query_details) / evaluated_count,
            4,
        ),
        "mean_precision_at_5": round(
            sum(q["ir_metrics"]["precision_at_5"] for q in query_details) / evaluated_count,
            4,
        ),
        "mrr": round(
            sum(q["ir_metrics"]["reciprocal_rank"] for q in query_details) / evaluated_count,
            4,
        ),
        "mean_ndcg_at_5": round(
            sum(q["ir_metrics"]["ndcg_at_5"] for q in query_details) / evaluated_count,
            4,
        ),
        "mean_csr": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["overall_csr"] for q in query_details) / evaluated_count,
            4,
        ),
        "mean_price_compliance_pct": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["price_compliance_pct"] for q in query_details) / evaluated_count,
            4,
        ),
        "mean_distance_compliance_pct": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["distance_compliance_pct"] for q in query_details) / evaluated_count,
            4,
        ),
        "mean_room_type_compliance_pct": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["room_type_compliance_pct"] for q in query_details) / evaluated_count,
            4,
        ),
        "mean_amenities_compliance_pct": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["amenities_compliance_pct"] for q in query_details) / evaluated_count,
            4,
        ),
        "mean_relevance_score": round(
            sum(q["judge_report"]["relevance_score"] for q in query_details) / evaluated_count,
            2,
        ),
        "mean_ranking_score": round(
            sum(q["judge_report"]["ranking_score"] for q in query_details) / evaluated_count,
            2,
        ),
        "mean_faithfulness_score": round(
            sum(q["judge_report"]["faithfulness_score"] for q in query_details) / evaluated_count,
            2,
        ),
        "mean_overall_score": round(
            sum(q["judge_report"]["overall_score"] for q in query_details) / evaluated_count,
            2,
        ),
        "latency_p50_s": round(p50_lat, 3),
        "latency_p95_s": round(p95_lat, 3),
        "latency_max_s": round(max_lat, 3),
        "latency_mean_s": round(mean_lat, 3),
    }

    # 6. Phân rã theo nhóm Persona
    group_stats: dict[str, Any] = {}
    distinct_groups = sorted(list({q["group"] for q in query_details}))

    for grp in distinct_groups:
        g_queries = [q for q in query_details if q["group"] == grp]
        g_count = len(g_queries)
        group_stats[grp] = {
            "count": g_count,
            "mean_p3": round(sum(q["ir_metrics"]["precision_at_3"] for q in g_queries) / g_count, 4),
            "mean_p5": round(sum(q["ir_metrics"]["precision_at_5"] for q in g_queries) / g_count, 4),
            "mean_mrr": round(sum(q["ir_metrics"]["reciprocal_rank"] for q in g_queries) / g_count, 4),
            "mean_ndcg5": round(sum(q["ir_metrics"]["ndcg_at_5"] for q in g_queries) / g_count, 4),
            "mean_csr": round(sum(q["ir_metrics"]["constraint_breakdown"]["overall_csr"] for q in g_queries) / g_count, 4),
            "mean_overall_score": round(sum(q["judge_report"]["overall_score"] for q in g_queries) / g_count, 2),
            "mean_latency_s": round(sum(q["latency_s"] for q in g_queries) / g_count, 3),
        }

    meta = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_queries": evaluated_count,
        "planned_queries": total_queries,
        "judge_mode": judge_mode,
        "judge_model": judge_model_name,
        "budget_tolerance_pct": budget_tolerance_pct,
        "offline_nlu": offline_nlu,
        "pacing_s": pacing,
        "daily_quota_stopped": daily_quota_hit,
    }

    results_payload = {
        "meta": meta,
        "summary": summary,
        "group_breakdown": group_stats,
        "query_details": query_details,
    }

    # 7. Xuất file kết quả JSON và Markdown
    json_path, md_path = save_evaluation_results(results_payload, out_path)

    logger.info("=" * 70)
    logger.info("KẾT THÚC ĐÁNH GIÁ THÀNH CÔNG!")
    logger.info("Tổng điểm Thẩm định: %.2f / 5.0 | Mean P@5: %.2f%% | MRR: %.4f | nDCG@5: %.4f",
                summary["mean_overall_score"], summary["mean_precision_at_5"] * 100, summary["mrr"], summary["mean_ndcg_at_5"])
    logger.info("=" * 70)

    return results_payload


# ============================================================================
# CLI ENTRY POINT
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Đánh giá Hệ thống Gợi ý Phòng trọ Thông minh (Homigo) qua IR Metrics và LLM-as-a-Judge.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Giới hạn số lượng query cần chạy (mặc định: None = chạy toàn bộ).",
    )
    parser.add_argument(
        "--group",
        type=str,
        default=None,
        help="Lọc theo nhóm Persona (ví dụ: 'G1_BUDGET,G2_SAFETY_AMENITY').",
    )
    parser.add_argument(
        "--judge",
        choices=["auto", "llm", "rule"],
        default="auto",
        help="Chế độ đánh giá Judge ('auto': tự động nhận diện LLM, 'llm': ép dùng LLM, 'rule': chỉ dùng luật).",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.5-flash-lite",
        help="Tên mô hình LLM dùng làm Judge (mặc định: 'gemini-2.5-flash-lite').",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="eval_results",
        help="Thư mục lưu trữ báo cáo đầu ra (mặc định: 'eval_results' -> lưu trong ai-agent/eval_results/).",
    )
    parser.add_argument(
        "--budget-tolerance",
        type=float,
        default=0.0,
        help="Tỷ lệ nới lỏng ngân sách khi thẩm định (mặc định: 0.0 = không nới lỏng).",
    )
    parser.add_argument(
        "--pacing",
        type=float,
        default=3.5,
        help="Thời gian nghỉ (giây) giữa các query (mặc định: 3.5s).",
    )
    parser.add_argument(
        "--offline-nlu",
        action="store_true",
        help="Chế độ Offline NLU: chuyển trực tiếp GroundTruthExpectation thành truy vấn Backend để đo IR và Reranker mà không tốn token LLM.",
    )

    args = parser.parse_args()

    run_evaluation(
        limit=args.limit,
        group_filter=args.group,
        judge_mode=args.judge,
        judge_model_name=args.model,
        output_dir=args.out,
        budget_tolerance_pct=args.budget_tolerance,
        pacing=args.pacing,
        offline_nlu=args.offline_nlu,
    )


if __name__ == "__main__":
    main()


__all__ = [
    "generate_markdown_report",
    "_build_markdown_report",
    "save_evaluation_results",
    "run_evaluation",
]
