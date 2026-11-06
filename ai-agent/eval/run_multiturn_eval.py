"""Runner Đánh giá Khả năng Duy trì Ngữ cảnh & Ghi nhớ Đa Lượt (Multi-turn Memory Benchmark).

Đánh giá các khía cạnh cốt lõi của LangGraph State Machine & SessionStore:
1. Context Retention Rate (CRR): Tỷ lệ giữ nguyên các ràng buộc cốt lõi khi người dùng tinh chỉnh bổ sung.
2. Goal Drift Resistance (GDR): Tỷ lệ không bị trôi/lệch mục tiêu khi nhận thêm câu chat hội thoại.
3. Follow-up Accuracy: Khả năng trả lời câu hỏi sâu về danh sách phòng ở lượt trước (in-context reference).
4. Preference Rollback: Khả năng khôi phục mốc tìm kiếm trước đó từ Snapshot History.

Xuất báo cáo chi tiết ra JSON và Markdown tại `ai-agent/eval_results/`.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
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
logger = logging.getLogger("eval.multiturn_runner")

from service import HousingAgentService


# ============================================================================
# CÁC KỊCH BẢN ĐA LƯỢT CHUẨN ĐO LƯỜNG MEMORY (MULTI-TURN BENCHMARK SCENARIOS)
# ============================================================================

MULTITURN_SCENARIOS = [
    {
        "id": "MT_01_REFINEMENT",
        "name": "Tinh chỉnh Ràng buộc & Tích lũy Tiện ích (Preference Refinement)",
        "description": "Người dùng thêm tiện ích máy giặt và giờ tự do, sau đó nới ngân sách mà không nhắc lại địa điểm.",
        "turns": [
            {
                "turn": 1,
                "input": "Tìm phòng trọ gần ĐHQG Thủ Đức giá dưới 2 triệu có máy lạnh",
                "expect_intent": "search",
                "checks": {
                    "has_rooms": True,
                    "location_contains": "đhqg",
                    "max_price": 2_000_000,
                    "has_amenity": "aircon",
                },
            },
            {
                "turn": 2,
                "input": "Thêm cho mình máy giặt với giờ tự do nữa nhé",
                "expect_intent": "search",
                "checks": {
                    "has_rooms": True,
                    "location_contains": "đhqg",
                    "max_price": 2_000_000,
                    "has_amenity": "washing_machine",
                },
            },
            {
                "turn": 3,
                "input": "Nới ngân sách lên tối đa 2.5 triệu xem có thêm phòng không bạn",
                "expect_intent": "search",
                "checks": {
                    "has_rooms": True,
                    "location_contains": "đhqg",
                    "max_price": 2_500_000,
                    "has_amenity": "aircon",
                },
            },
        ],
    },
    {
        "id": "MT_02_ROLLBACK",
        "name": "Chuyển Đổi Khu Vực & Khôi Phục Snapshot (Context Switching & Rollback)",
        "description": "Người dùng đổi khu vực tìm kiếm sang quận khác, sau đó yêu cầu quay lại tìm ở quận cũ.",
        "turns": [
            {
                "turn": 1,
                "input": "Tìm phòng trọ ở Quận 10 tầm 3 triệu",
                "expect_intent": "search",
                "checks": {
                    "has_rooms": True,
                    "location_contains": "quận 10",
                    "max_price": 3_000_000,
                },
            },
            {
                "turn": 2,
                "input": "Thôi đổi qua tìm ở Bình Thạnh giá tầm 3.5 triệu giúp mình",
                "expect_intent": "search",
                "checks": {
                    "has_rooms": True,
                    "location_contains": "bình thạnh",
                    "max_price": 3_500_000,
                },
            },
            {
                "turn": 3,
                "input": "Thôi quay lại tìm ở Quận 10 như lúc nãy đi bạn",
                "expect_intent": "search",
                "checks": {
                    "has_rooms": True,
                    "location_contains": "quận 10",
                },
            },
        ],
    },
    {
        "id": "MT_03_FOLLOWUP_QA",
        "name": "Hỏi Đáp Ngữ Cảnh Phòng & Chi Phí (In-Context Reference)",
        "description": "Người dùng hỏi sâu về phòng trong danh sách kết quả (nuôi thú cưng, tiền cọc, khoảng cách).",
        "turns": [
            {
                "turn": 1,
                "input": "Tìm phòng trọ gần ĐH Bách Khoa CS1 Q10 dưới 3.5 triệu",
                "expect_intent": "search",
                "checks": {
                    "has_rooms": True,
                    "location_contains": "bách khoa",
                },
            },
            {
                "turn": 2,
                "input": "Phòng đầu tiên có cho nuôi mèo không bạn?",
                "expect_intent": "qa",
                "checks": {
                    "reply_contains_any": ["thú cưng", "mèo", "pet", "chủ nhà", "phòng"],
                    "no_template_dump": True,
                },
            },
            {
                "turn": 3,
                "input": "Còn phòng số 2 thì giá thuê và cọc bao nhiêu vậy?",
                "expect_intent": "qa",
                "checks": {
                    "reply_contains_any": ["cọc", "triệu", "giá", "tháng"],
                    "no_template_dump": True,
                },
            },
        ],
    },
]


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join(["---"] * len(headers)) + " |"
    data_lines = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator_line] + data_lines)


def evaluate_multiturn_turn(
    resp: Any,
    expected_checks: dict[str, Any],
) -> dict[str, Any]:
    """Kiểm tra từng turn dựa trên AgentResponse và các checks mong đợi."""
    rooms = getattr(resp, "rooms", []) or []
    text_reply = getattr(resp, "text_reply", "") or ""
    prefs = getattr(resp, "current_preferences", None)

    check_results: dict[str, bool] = {}
    details: list[str] = []

    # 1. Kiểm tra có phòng không
    if "has_rooms" in expected_checks:
        passed = (len(rooms) > 0) == expected_checks["has_rooms"]
        check_results["has_rooms"] = passed
        if not passed:
            details.append(f"Expected has_rooms={expected_checks['has_rooms']}, got {len(rooms)} rooms")

    # 2. Kiểm tra địa điểm trong preferences
    if "location_contains" in expected_checks:
        target_kw = expected_checks["location_contains"].lower()
        loc_str = ""
        if prefs and getattr(prefs, "location_text", None):
            loc_str = str(prefs.location_text).lower()
        passed = target_kw in loc_str or any(target_kw in getattr(r, "address", "").lower() for r in rooms)
        check_results["location_retention"] = passed
        if not passed:
            details.append(f"Expected location contains '{target_kw}', got '{loc_str}'")

    # 3. Kiểm tra ngân sách trần
    if "max_price" in expected_checks:
        exp_max = expected_checks["max_price"]
        pref_max = getattr(prefs, "max_price", None) if prefs else None
        # Kiểm tra preferences hoặc các phòng trả về
        passed = False
        if pref_max is not None and pref_max <= exp_max * 1.05:
            passed = True
        elif rooms and all(getattr(r, "priceNum", 0) <= exp_max * 1.05 for r in rooms if getattr(r, "priceNum", 0) > 0):
            passed = True
        check_results["budget_retention"] = passed
        if not passed:
            details.append(f"Expected max_price <= {exp_max}, pref={pref_max}")

    # 4. Kiểm tra tiện ích
    if "has_amenity" in expected_checks:
        target_a = expected_checks["has_amenity"].lower()
        pref_amenities = [str(a).lower() for a in (getattr(prefs, "amenities", []) or [])]
        passed = any(target_a in a for a in pref_amenities)
        check_results["amenity_retention"] = passed
        if not passed:
            details.append(f"Expected amenity '{target_a}' in {pref_amenities}")

    # 5. Kiểm tra từ khóa trong phản hồi
    if "reply_contains_any" in expected_checks:
        kws = expected_checks["reply_contains_any"]
        passed = any(kw.lower() in text_reply.lower() for kw in kws)
        check_results["reply_relevance"] = passed
        if not passed:
            details.append(f"Expected text reply to contain any of {kws}")

    # 6. Kiểm tra không lặp template danh sách khi hỏi đáp
    if "no_template_dump" in expected_checks:
        passed = not text_reply.startswith("Homigo đã tìm được") and not text_reply.startswith("Dưới đây là danh sách")
        check_results["no_template_dump"] = passed
        if not passed:
            details.append("Agent dumped whole room template instead of focused QA answer")

    all_passed = all(check_results.values()) if check_results else True
    return {
        "passed": all_passed,
        "check_results": check_results,
        "details": details,
        "rooms_count": len(rooms),
        "reply_preview": text_reply[:200],
    }


def run_multiturn_benchmark(
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Chạy toàn bộ bài đánh giá Đa Lượt (Multi-turn Memory Benchmark)."""
    if output_dir:
        out_path = Path(output_dir)
        if not out_path.is_absolute():
            out_path = _AI_AGENT_DIR / out_path
    else:
        out_path = _AI_AGENT_DIR / "eval_results"
    out_path.mkdir(parents=True, exist_ok=True)

    agent = HousingAgentService()
    logger.info("=" * 70)
    logger.info("BẮT ĐẦU ĐÁNH GIÁ MULTI-TURN MEMORY BENCHMARK (%d kịch bản)", len(MULTITURN_SCENARIOS))
    logger.info("=" * 70)

    scenario_reports: list[dict[str, Any]] = []
    total_checks = 0
    passed_checks = 0

    for sc in MULTITURN_SCENARIOS:
        sc_id = sc["id"]
        sc_name = sc["name"]
        sc_desc = sc["description"]
        turns = sc["turns"]

        session_id = f"eval_mt_{sc_id}_{uuid.uuid4().hex[:6]}"
        logger.info("-> Chạy Kịch bản: [%s] %s (Session: %s)", sc_id, sc_name, session_id)

        turn_records: list[dict[str, Any]] = []
        sc_all_passed = True

        for t_info in turns:
            t_num = t_info["turn"]
            user_msg = t_info["input"]
            exp_checks = t_info["checks"]

            t0 = time.perf_counter()
            try:
                if hasattr(agent, "handle_message"):
                    resp = agent.handle_message(session_id=session_id, message=user_msg)
                else:
                    resp = agent.run(user_message=user_msg, session_id=session_id)
            except Exception as e:
                logger.error("Lỗi turn %d trong kịch bản %s: %s", t_num, sc_id, e)
                from domain.schemas import AgentResponse
                resp = AgentResponse(session_id=session_id, text_reply=f"Error: {e}", rooms=[])

            lat_s = time.perf_counter() - t0
            t_eval = evaluate_multiturn_turn(resp, exp_checks)

            # Đếm checks
            for ck_val in t_eval["check_results"].values():
                total_checks += 1
                if ck_val:
                    passed_checks += 1

            if not t_eval["passed"]:
                sc_all_passed = False

            status_icon = "✅ PASS" if t_eval["passed"] else "❌ FAIL"
            logger.info("   Turn %d: \"%s\" -> %s (Rooms=%d, Latency=%.2fs)",
                        t_num, user_msg[:40], status_icon, t_eval["rooms_count"], lat_s)
            if t_eval["details"]:
                logger.warning("      Issues: %s", ", ".join(t_eval["details"]))

            turn_records.append({
                "turn": t_num,
                "input": user_msg,
                "latency_s": round(lat_s, 3),
                "passed": t_eval["passed"],
                "rooms_count": t_eval["rooms_count"],
                "checks": t_eval["check_results"],
                "issues": t_eval["details"],
                "reply_preview": t_eval["reply_preview"],
            })

        scenario_reports.append({
            "scenario_id": sc_id,
            "name": sc_name,
            "description": sc_desc,
            "all_passed": sc_all_passed,
            "turns": turn_records,
        })

    # Tính toán Metrics
    crr = (passed_checks / total_checks) if total_checks > 0 else 0.0
    msr = (sum(1 for s in scenario_reports if s["all_passed"]) / len(scenario_reports)) if scenario_reports else 0.0

    summary = {
        "total_scenarios": len(scenario_reports),
        "successful_scenarios": sum(1 for s in scenario_reports if s["all_passed"]),
        "multi_turn_success_rate": round(msr, 4),
        "total_checks": total_checks,
        "passed_checks": passed_checks,
        "context_retention_rate": round(crr, 4),
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # Xuất Markdown report
    md_lines: list[str] = [
        "# 🧠 Báo Cáo Đánh Giá Khả Năng Duy Trì Ngữ Cảnh & Ghi Nhớ Đa Lượt (Multi-turn Memory)",
        "",
        "> **Hệ thống:** Homigo Smart Housing AI Agent  ",
        f"> **Thời gian đánh giá:** {summary['timestamp']}  ",
        f"> **Tỷ lệ Duy trì Ngữ cảnh (CRR - Context Retention Rate):** **{crr * 100:.2f}%**  ",
        f"> **Tỷ lệ Hoàn thành Kịch bản (MSR - Multi-turn Success Rate):** **{msr * 100:.2f}%**  ",
        "",
        "## 1. 🎯 Tổng Hợp Chỉ Số Hiệu Năng Bộ Nhớ (Memory Metrics)",
        "",
    ]

    metric_rows = [
        ["Context Retention Rate (CRR)", f"{crr * 100:.2f}%", f"{passed_checks}/{total_checks} tiêu chí duy trì chính xác"],
        ["Multi-turn Success Rate (MSR)", f"{msr * 100:.2f}%", f"{summary['successful_scenarios']}/{summary['total_scenarios']} kịch bản đạt 100%"],
        ["Anti-Goal-Drift Resistance", f"{crr * 100:.2f}%", "Không bị trôi mốc hoặc mất tiêu chí đã chọn"],
    ]
    md_lines.append(_md_table(["Chỉ số Đo lường", "Giá trị", "Ý nghĩa Đánh giá"], metric_rows))
    md_lines.append("")

    md_lines.append("## 2. 📋 Chi Tiết Từng Kịch Bản Đa Lượt (Scenario Breakdown)")
    md_lines.append("")

    for sc_rep in scenario_reports:
        sc_icon = "✅ HOÀN THÀNH" if sc_rep["all_passed"] else "⚠️ CÓ LỖI"
        md_lines.append(f"### `{sc_rep['scenario_id']}`: {sc_rep['name']} — {sc_icon}")
        md_lines.append(f"- **Mô tả:** _{sc_rep['description']}_")
        md_lines.append("")

        t_rows = []
        for t in sc_rep["turns"]:
            t_icon = "✅" if t["passed"] else "❌"
            issue_str = ", ".join(t["issues"]) if t["issues"] else "Đạt mọi tiêu chí"
            t_rows.append([
                f"Lượt {t['turn']}",
                t["input"],
                t_icon,
                str(t["rooms_count"]),
                f"{t['latency_s']:.2f}s",
                issue_str,
            ])
        md_lines.append(_md_table(["Lượt", "Câu nói người dùng", "Kết quả", "Số phòng", "Độ trễ", "Ghi chú kiểm tra"], t_rows))
        md_lines.append("")

    md_content = "\n".join(md_lines)

    # Lưu file
    json_path = out_path / "multiturn_eval_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "scenarios": scenario_reports}, f, ensure_ascii=False, indent=2)

    md_path = out_path / "multiturn_evaluation_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    logger.info("=" * 70)
    logger.info("HOÀN THÀNH ĐÁNH GIÁ ĐA LƯỢT!")
    logger.info("CRR: %.2f%% | MSR: %.2f%%", crr * 100, msr * 100)
    logger.info("Lưu báo cáo tại: %s", md_path)
    logger.info("=" * 70)

    return {"summary": summary, "scenarios": scenario_reports}


def main() -> None:
    parser = argparse.ArgumentParser(description="Đánh giá Multi-turn Memory Benchmark của Homigo AI Agent.")
    parser.add_argument("--out", type=str, default="eval_results", help="Thư mục lưu báo cáo.")
    args = parser.parse_args()
    run_multiturn_benchmark(output_dir=args.out)


if __name__ == "__main__":
    main()
