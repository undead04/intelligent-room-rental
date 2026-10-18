import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.model.llm.client import GeminiRoundRobin, call_gemini_chunk
from crawler.schema.listing import ChunkExtractionWrapper



def process_chunk_result(
    parsed: ChunkExtractionWrapper,
    chunk: List[Dict[str, Any]],
    checkpoint: Dict[str, Dict[str, Any]],
    clean_results: List[Dict[str, Any]],
    chunk_label: str,
) -> Set[str]:
    """
    Xử lý kết quả trả về từ Gemini:
    - So khớp ID
    - Chạy verify_evidence chống hallucination
    - Tính sẵn concept_scores, amenity_overall_score, safety_score
    - Cập nhật checkpoint & clean_results
    """
    expected_ids = {str(a.get("listing_id") or a.get("id")) for a in chunk}
    text_map = {str(a.get("listing_id") or a.get("id")): (a.get("text") or a.get("description", "")) for a in chunk}

    returned_ids: Set[str] = set()
    newly_extracted_ids: Set[str] = set()

    for item in parsed.reports:
        art_id = str(item.id)
        returned_ids.add(art_id)

        if art_id in checkpoint:
            continue

        report_dict = None
        if item.report:
            # Chạy xác thực evidence chống bịa đặt
            source_text = text_map.get(art_id, "")
            verified_report = item.report.verify_evidence(source_text) if source_text else item.report

            report_dict = verified_report.model_dump(mode="json")
            # Gắn các điểm tính toán tiện ích và an toàn
            report_dict["amenity_overall_score"] = verified_report.amenity_overall_score()
            report_dict["safety_score"] = verified_report.safety_score()
            report_dict["concept_scores"] = verified_report.to_concept_scores()

        result = {
            "listing_id": art_id,
            "report": report_dict,
        }

        checkpoint[art_id] = result
        clean_results.append(result)
        newly_extracted_ids.add(art_id)

    missing_ids = expected_ids - returned_ids
    if missing_ids:
        print(f"  [CANH BAO] [{chunk_label}] LLM bỏ sót các ID: {missing_ids}")

    print(
        f"  [OK] [{chunk_label}] Trích xuất {len(newly_extracted_ids)}/{len(chunk)} bài mới | "
        f"Tổng checkpoint: {len(checkpoint)} bài"
    )

    return newly_extracted_ids


def process_one_chunk(
    chunk: List[Dict[str, Any]],
    chunk_label: str,
    api_manager: GeminiRoundRobin,
    checkpoint: Dict[str, Dict[str, Any]],
    clean_results: List[Dict[str, Any]],
    failed_chunks: List[List[Dict[str, Any]]],
    system_prompt: str,
    max_retries: int,
    rpm_delay: float,
) -> bool:
    """Xử lý một chunk chứa các bài đăng chưa có trong checkpoint."""
    pending = [
        a for a in chunk
        if str(a.get("listing_id") or a.get("id")) not in checkpoint
    ]

    if not pending:
        return True

    parsed = call_gemini_chunk(
        api_manager=api_manager,
        chunk=pending,
        system_prompt=system_prompt,
        max_retries=max_retries,
        rpm_delay=rpm_delay,
    )

    if parsed is None:
        failed_chunks.append(pending)
        print(
            f"  [LOI] [{chunk_label}] Thất bại, đưa {len(pending)} bài vào failed_chunks "
            f"({len(failed_chunks)} chunk lỗi)"
        )
        return False

    process_chunk_result(
        parsed=parsed,
        chunk=pending,
        checkpoint=checkpoint,
        clean_results=clean_results,
        chunk_label=chunk_label,
    )
    return True
