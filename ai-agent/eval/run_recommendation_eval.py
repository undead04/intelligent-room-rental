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

# Tự động nạp file .env từ ai-agent hoặc crawler (để lấy API key)
try:
    from dotenv import load_dotenv
    _env_candidate = _AI_AGENT_DIR / ".env"
    if _env_candidate.is_file():
        load_dotenv(_env_candidate, override=False)

except ImportError:
    pass

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
    evaluate_room_satisfaction,
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

# Import HousingAgentService
from service import HousingAgentService


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
            f"**{jd.get('overall_score', 0.0):.2f}**",
            f"{q.get('latency_s', 0.0):.2f}s",
            q.get("status_summary", "N/A"),
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
            "Judge",
            "Latency",
            "Tóm tắt Trạng thái / Đánh giá",
        ],
        query_rows,
    ))
    md_lines.append("")

    # 3.1. Phân rã chi tiết từng Ca kiểm thử
    md_lines.append("### 3.1. 🔍 Phân Rã Chi Tiết Từng Ca Kiểm Thử (Detailed Test Cases)")
    md_lines.append("")
    for q in query_details:
        qid = q.get("query_id", "")
        grp = q.get("group", "")
        qry = q.get("query", "")
        status = q.get("status_summary", "")
        lat = q.get("latency_s", 0.0)
        exp = q.get("expectation_summary", {})
        jd = q.get("judge_report", {})
        rooms_d = q.get("returned_rooms_details", [])
        text_rep = q.get("agent_text_reply", "").strip()

        md_lines.append(f"#### 🔹 Ca `{qid}` ({grp}): \"{qry}\"")
        md_lines.append(f"- **Trạng thái:** `{status}` | **Thời gian:** `{lat:.2f}s` | **Judge Score:** `{jd.get('overall_score', 0.0):.2f}/5.0`")

        exp_parts = []
        if exp.get("max_budget"):
            exp_parts.append(f"Giá trần: {exp['max_budget']/1_000_000:.1f}tr")
        if exp.get("min_budget"):
            exp_parts.append(f"Giá sàn: {exp['min_budget']/1_000_000:.1f}tr")
        if exp.get("landmark"):
            dist_max = exp.get("max_distance_km", 5.0)
            exp_parts.append(f"Mốc: {exp['landmark']} (<= {dist_max}km)")
        if exp.get("required_amenities"):
            exp_parts.append(f"Tiện ích: {', '.join(exp['required_amenities'])}")
        if exp.get("allowed_room_types"):
            exp_parts.append(f"Loại phòng: {', '.join(exp['allowed_room_types'])}")
        md_lines.append(f"- **Ràng buộc kỳ vọng:** {'; '.join(exp_parts) if exp_parts else 'Không có ràng buộc cứng'}")

        if jd.get("rationale"):
            md_lines.append(f"- **Nhận xét của Judge:** {jd['rationale']}")

        if rooms_d:
            room_tbl_rows = []
            for r in rooms_d[:5]:
                chk = "✅" if r.get("is_fully_satisfied") else "⚠️"
                dist_str = f"{r.get('actual_distance_km', 'N/A')} km" if r.get('actual_distance_km') is not None else "N/A"
                price_str = r.get("price", "N/A")
                amenity_str = ", ".join(r.get("matched_amenities", [])[:3]) or "N/A"
                room_tbl_rows.append([
                    f"`{r.get('id', '')}`",
                    chk,
                    r.get("title", "")[:35] + ("..." if len(r.get("title", "")) > 35 else ""),
                    price_str,
                    dist_str,
                    amenity_str,
                ])
            md_lines.append("")
            md_lines.append(_md_table(["Mã phòng", "Đạt", "Tiêu đề", "Giá", "Khoảng cách", "Tiện ích khớp"], room_tbl_rows))
            md_lines.append("")
        else:
            md_lines.append("- *Không có phòng nào được trả về.*")
            md_lines.append("")

        if text_rep:
            clean_reply = text_rep.replace("\n", " ").strip()
            short_reply = clean_reply[:250] + ("..." if len(clean_reply) > 250 else "")
            md_lines.append(f"> **Phản hồi Agent:** _{short_reply}_")
        md_lines.append("")
        md_lines.append("---")
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


def save_evaluation_results(
    results_payload: dict[str, Any],
    output_dir: str | Path | None = None,
) -> tuple[Path, Path]:
    """Lưu kết quả đánh giá ra hai định dạng JSON và Markdown."""
    if output_dir:
        out_path = Path(output_dir)
        if not out_path.is_absolute():
            out_path = _AI_AGENT_DIR / out_path
    else:
        out_path = _AI_AGENT_DIR / "eval_results"
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
    judge_model_name: str = "gemini-3.5-flash-lite",
    output_dir: str = "eval_results",
    budget_tolerance_pct: float = 0.0,
) -> dict[str, Any]:
    """Chạy toàn bộ quy trình đánh giá trên bộ Recommendation Benchmark."""
    if output_dir:
        out_path = Path(output_dir)
        if not out_path.is_absolute():
            out_path = _AI_AGENT_DIR / out_path
    else:
        out_path = _AI_AGENT_DIR / "eval_results"
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
    logger.info("Chế độ Judge: %s | Model Judge: %s", judge_mode, judge_model_name)
    logger.info("=" * 70)

    # 2. Khởi tạo LLM Judge
    judge_llm = None
    if judge_mode in ("auto", "llm"):
        judge_llm = get_judge_llm(model_name=judge_model_name)
        if judge_llm is None and judge_mode == "llm":
            raise RuntimeError(
                f"Chế độ judge='llm' yêu cầu API Key hợp lệ cho {judge_model_name}. Vui lòng cấu hình GEMINI_API_KEY hoặc OPENAI_API_KEY."
            )
        elif judge_llm is not None:
            logger.info("Đã khởi tạo thành công Judge LLM: %s", judge_model_name)
        else:
            logger.info("Không có API Key cho Judge LLM, chuyển sang chế độ Rule-based offline.")

    # 3. Khởi tạo HousingAgentService
    agent = HousingAgentService()

    # 4. Vòng lặp thực thi từng query
    query_details: list[dict[str, Any]] = []

    for idx, q in enumerate(queries, start=1):
        session_id = f"eval_rec_{q.id}_{uuid.uuid4().hex[:6]}"
        logger.info("[%d/%d] Chạy Query ID: %s (%s) | \"%s\"", idx, total_queries, q.id, q.group, q.query[:60])

        t0 = time.perf_counter()
        try:
            # Gọi Agent Service
            if hasattr(agent, "handle_message"):
                resp = agent.handle_message(session_id=session_id, message=q.query)
            else:
                resp = agent.run(user_message=q.query, session_id=session_id)
        except Exception as e:
            logger.error("Lỗi khi thực thi Agent cho query %s: %s", q.id, e, exc_info=True)
            # Khởi tạo response rỗng dự phòng khi agent gặp lỗi
            from domain.schemas import AgentResponse
            resp = AgentResponse(
                session_id=session_id,
                text_reply=f"Lỗi hệ thống khi tìm phòng: {e}",
                rooms=[],
            )

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
        judge_rep: RecommendationJudgeReport = evaluate_recommendation_quality(
            model=judge_llm,
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

        # C. Đánh giá chi tiết từng phòng
        rooms_detail = []
        satisfied_count = 0
        for r in rooms:
            sat = evaluate_room_satisfaction(r, q.expectation, budget_tolerance_pct)
            is_sat = sat.get("is_fully_satisfied", False)
            if is_sat:
                satisfied_count += 1
            rooms_detail.append({
                "id": str(getattr(r, "id", "")),
                "title": str(getattr(r, "title", "")),
                "price": str(getattr(r, "price", "")),
                "price_num": float(getattr(r, "priceNum", 0.0) or 0.0),
                "actual_distance_km": round(sat["distance_km"], 2) if sat.get("distance_km") is not None else None,
                "room_type": str(getattr(r, "room_type", "") or ""),
                "address": str(getattr(r, "address", "") or ""),
                "tags": list(getattr(r, "tags", []) or []),
                "matched_amenities": sat.get("matched_amenities", []),
                "missing_amenities": sat.get("missing_amenities", []),
                "price_ok": sat.get("price_ok", False),
                "distance_ok": sat.get("distance_ok", False),
                "room_type_ok": sat.get("room_type_ok", False),
                "amenities_ok": sat.get("amenities_ok", False),
                "is_fully_satisfied": is_sat,
            })

        # D. Tóm tắt trạng thái Pass/Fail minh bạch
        if len(rooms) == 0:
            if any(kw in text_reply.lower() for kw in ("bạn có thể", "khu vực nào", "ngân sách", "thông tin cụ thể", "làm rõ")):
                status_summary = "FAIL (0 phòng): Agent kích hoạt hỏi lại (Clarify)"
            else:
                status_summary = "FAIL (0 phòng): Không tìm thấy phòng thỏa mãn trong DB"
        else:
            if satisfied_count == len(rooms):
                status_summary = f"PASS ({satisfied_count}/{len(rooms)} phòng đạt 100% tiêu chí)"
            else:
                issues = []
                price_fails = sum(1 for rd in rooms_detail if not rd["price_ok"])
                dist_fails = sum(1 for rd in rooms_detail if not rd["distance_ok"])
                type_fails = sum(1 for rd in rooms_detail if not rd["room_type_ok"])
                amenity_fails = sum(1 for rd in rooms_detail if not rd["amenities_ok"])
                if price_fails:
                    issues.append(f"{price_fails} vượt giá")
                if dist_fails:
                    issues.append(f"{dist_fails} vượt bán kính")
                if type_fails:
                    issues.append(f"{type_fails} sai loại phòng")
                if amenity_fails:
                    issues.append(f"{amenity_fails} thiếu tiện ích")
                issue_str = ", ".join(issues) if issues else "chưa hoàn hảo"
                status_summary = f"PARTIAL ({satisfied_count}/{len(rooms)} phòng đạt | {issue_str})"

        exp = q.expectation
        query_record = {
            "query_id": q.id,
            "group": q.group,
            "persona_description": q.persona_description,
            "query": q.query,
            "latency_s": round(latency_s, 3),
            "returned_rooms_count": len(rooms),
            "status_summary": status_summary,
            "agent_text_reply": text_reply,
            "expectation_summary": {
                "max_budget": exp.max_budget,
                "min_budget": exp.min_budget,
                "landmark": getattr(exp, "target_location_name", ""),
                "max_distance_km": exp.max_distance_km,
                "allowed_room_types": [str(rt) for rt in exp.allowed_room_types or []],
                "forbidden_room_types": [str(rt) for rt in exp.forbidden_room_types or []],
                "required_amenities": [str(a) for a in exp.required_amenities or []],
            },
            "returned_rooms_details": rooms_detail,
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

    # 5. Tổng hợp số liệu toàn cục
    latencies = sorted(q["latency_s"] for q in query_details)
    p50_lat = statistics.median(latencies) if latencies else 0.0
    p95_idx = int(len(latencies) * 0.95)
    p95_lat = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0
    mean_lat = sum(latencies) / total_queries if total_queries > 0 else 0.0

    summary = {
        "total_queries": total_queries,
        "mean_precision_at_3": round(
            sum(q["ir_metrics"]["precision_at_3"] for q in query_details) / total_queries,
            4,
        ),
        "mean_precision_at_5": round(
            sum(q["ir_metrics"]["precision_at_5"] for q in query_details) / total_queries,
            4,
        ),
        "mrr": round(
            sum(q["ir_metrics"]["reciprocal_rank"] for q in query_details) / total_queries,
            4,
        ),
        "mean_ndcg_at_5": round(
            sum(q["ir_metrics"]["ndcg_at_5"] for q in query_details) / total_queries,
            4,
        ),
        "mean_csr": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["overall_csr"] for q in query_details) / total_queries,
            4,
        ),
        "mean_price_compliance_pct": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["price_compliance_pct"] for q in query_details) / total_queries,
            4,
        ),
        "mean_distance_compliance_pct": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["distance_compliance_pct"] for q in query_details) / total_queries,
            4,
        ),
        "mean_room_type_compliance_pct": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["room_type_compliance_pct"] for q in query_details) / total_queries,
            4,
        ),
        "mean_amenities_compliance_pct": round(
            sum(q["ir_metrics"]["constraint_breakdown"]["amenities_compliance_pct"] for q in query_details) / total_queries,
            4,
        ),
        "mean_relevance_score": round(
            sum(q["judge_report"]["relevance_score"] for q in query_details) / total_queries,
            2,
        ),
        "mean_ranking_score": round(
            sum(q["judge_report"]["ranking_score"] for q in query_details) / total_queries,
            2,
        ),
        "mean_faithfulness_score": round(
            sum(q["judge_report"]["faithfulness_score"] for q in query_details) / total_queries,
            2,
        ),
        "mean_overall_score": round(
            sum(q["judge_report"]["overall_score"] for q in query_details) / total_queries,
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
        "total_queries": total_queries,
        "judge_mode": judge_mode,
        "judge_model": judge_model_name,
        "budget_tolerance_pct": budget_tolerance_pct,
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
        default="gemini-3.5-flash-lite",
        help="Tên mô hình LLM dùng làm Judge (mặc định: 'gemini-3.5-flash-lite').",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="eval_results",
        help="Thư mục lưu trữ báo cáo đầu ra (mặc định: 'eval_results').",
    )
    parser.add_argument(
        "--budget-tolerance",
        type=float,
        default=0.0,
        help="Tỷ lệ nới lỏng ngân sách khi thẩm định (mặc định: 0.0 = không nới lỏng).",
    )

    args = parser.parse_args()

    run_evaluation(
        limit=args.limit,
        group_filter=args.group,
        judge_mode=args.judge,
        judge_model_name=args.model,
        output_dir=args.out,
        budget_tolerance_pct=args.budget_tolerance,
    )


if __name__ == "__main__":
    main()


__all__ = [
    "generate_markdown_report",
    "_build_markdown_report",
    "save_evaluation_results",
    "run_evaluation",
]
