import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from google.genai import types

try:
    from crawler.model.gemini_robin import GeminiRoundRobin
    from crawler.model.system_prompt import SYSTEM_PROMPT, build_ai_contents
    from crawler.model.create_dynamic_chunks import create_dynamic_chunks
    from crawler.schema.listing import ChunkExtractionWrapper
except ImportError:
    from gemini_robin import GeminiRoundRobin
    from system_prompt import SYSTEM_PROMPT, build_ai_contents
    from create_dynamic_chunks import create_dynamic_chunks
    from schema.listing import ChunkExtractionWrapper


# ============================================================
# CONFIG / CONSTANTS
# ============================================================
DEFAULT_MODEL = "gemini-2.0-flash-lite"
DEFAULT_RPM_DELAY = 4.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_MAX_TOKENS_PER_CHUNK = 2500


# ============================================================
# ERROR HANDLING
# ============================================================
def is_quota_error(exc: Exception) -> bool:
    """Kiểm tra exception có khả năng là quota / rate-limit hay không."""
    message = str(exc).lower()
    quota_keywords = [
        "quota",
        "rate limit",
        "ratelimit",
        "resource exhausted",
        "resource_exhausted",
        "too many requests",
        "429",
    ]
    return any(keyword in message for keyword in quota_keywords)


# ============================================================
# CHECKPOINT MANAGEMENT (ATOMIC & METADATA-AWARE)
# ============================================================
def load_checkpoint(
    checkpoint_path: Optional[Path],
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Set[int]]:
    """
    Tải checkpoint cũ và thông tin tiến độ đã chạy.
    Hỗ trợ cả format cũ (list dict) và format mới (object có metadata).

    Returns:
        checkpoint: mapping {listing_id: result_dict}
        clean_results: list các kết quả trích xuất
        metadata: dict thông tin metadata (chunk cuối, tổng chunk...)
        completed_chunk_indices: tập các index chunk đã xử lý xong
    """
    checkpoint: Dict[str, Dict[str, Any]] = {}
    clean_results: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
    completed_chunks: Set[int] = set()

    if checkpoint_path is None:
        return checkpoint, clean_results, metadata, completed_chunks

    checkpoint_path = Path(checkpoint_path)
    if not checkpoint_path.exists():
        return checkpoint, clean_results, metadata, completed_chunks

    try:
        raw_text = checkpoint_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return checkpoint, clean_results, metadata, completed_chunks
        raw_data = json.loads(raw_text)
    except Exception as e:
        print(f"[CANH BAO] Không thể đọc checkpoint từ {checkpoint_path}: {e}")
        return checkpoint, clean_results, metadata, completed_chunks

    if isinstance(raw_data, list):
        # Format cũ (mảng thuần kết quả)
        for prev in raw_data:
            listing_id = str(prev.get("listing_id") or prev.get("id"))
            checkpoint[listing_id] = prev
            clean_results.append(prev)
    elif isinstance(raw_data, dict):
        # Format mới (có metadata)
        metadata = raw_data.get("metadata", {})
        completed_chunks = set(metadata.get("completed_chunk_indices", []))
        for prev in raw_data.get("results", []):
            listing_id = str(prev.get("listing_id") or prev.get("id"))
            checkpoint[listing_id] = prev
            clean_results.append(prev)

    last_chunk = metadata.get("last_processed_chunk", len(completed_chunks))
    total_chunks = metadata.get("total_chunks", "?")

    print(
        f"[RESUME] Đã nạp {len(checkpoint)} bài từ checkpoint: {checkpoint_path}\n"
        f"         Tiến độ: Đã xong Chunk {last_chunk}/{total_chunks} "
        f"({len(completed_chunks)} chunks hoàn tất)"
    )

    return checkpoint, clean_results, metadata, completed_chunks


def save_checkpoint(
    checkpoint_path: Optional[Path],
    clean_results: List[Dict[str, Any]],
    metadata: Optional[Dict[str, Any]] = None,
    failed_chunks: Optional[List[List[Dict[str, Any]]]] = None,
) -> None:
    """
    Ghi checkpoint an toàn tuyệt đối (Atomic Write qua file tạm .tmp).
    Lưu rõ metadata: chunk hiện tại, tổng chunk, tổng bài và thời gian cập nhật.
    """
    if checkpoint_path is None:
        return

    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    failed_ids = []
    if failed_chunks:
        for chunk in failed_chunks:
            for a in chunk:
                art_id = str(a.get("listing_id") or a.get("id"))
                if art_id:
                    failed_ids.append(art_id)

    payload = {
        "metadata": metadata or {},
        "results": clean_results,
        "failed_listing_ids": sorted(list(set(failed_ids))),
    }

    # Atomic write: ghi ra .tmp trước rồi rename để tránh crash làm hỏng file
    tmp_path = checkpoint_path.with_suffix(f"{checkpoint_path.suffix}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if tmp_path.exists():
            tmp_path.replace(checkpoint_path)
    except Exception as e:
        print(f"[LOI] Không thể lưu checkpoint: {e}")


# ============================================================
# GEMINI API CALL
# ============================================================
def call_gemini_chunk(
    api_manager: GeminiRoundRobin,
    chunk: List[Dict[str, Any]],
    system_prompt: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    rpm_delay: float = DEFAULT_RPM_DELAY,
) -> Optional[ChunkExtractionWrapper]:
    """Gọi Gemini API trích xuất một chunk các bài đăng."""
    chunk_payload = [
        {
            "id": str(a.get("listing_id") or a.get("id")),
            "text": a.get("text") or a.get("description", ""),
        }
        for a in chunk
    ]

    contents = build_ai_contents(
        json.dumps(chunk_payload, ensure_ascii=False)
    )

    attempt = 0

    while True:
        try:
            print(
                f"  [API] Key {api_manager.current_key_number}/{api_manager.total_keys} "
                f"| Model: {api_manager.model_name}"
            )

            response = (
                api_manager.current_client
                .models
                .generate_content(
                    model=api_manager.model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=ChunkExtractionWrapper,
                        temperature=0.0,
                    ),
                )
            )

            raw_text = (response.text or "").strip()
            # Bóc tách nếu response bị model bọc trong ```json ... ```
            if raw_text.startswith("```"):
                lines = raw_text.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_text = "\n".join(lines).strip()

            return ChunkExtractionWrapper.model_validate_json(raw_text)

        except Exception as e:
            # QUOTA / RATE LIMIT -> Xoay vòng key
            if is_quota_error(e):
                print(
                    f"  [QUOTA] API Key {api_manager.current_key_number} "
                    f"chạm giới hạn quota / rate-limit."
                )
                has_next_key = api_manager.rotate()
                if has_next_key:
                    continue
                print("  [QUOTA] Tất cả API keys đều đã cạn quota.")
                return None

            # LỖI KHÁC -> Exponential backoff retry
            attempt += 1
            if attempt <= max_retries:
                wait = rpm_delay * (2 ** (attempt - 1))
                print(f"  [CANH BAO] Lần thử {attempt} gặp lỗi: {e}")
                print(f"  [RETRY] Đợi {wait:.1f}s trước khi thử lại...")
                time.sleep(wait)
                continue

            print(f"  [LOI] Thất bại sau {max_retries + 1} lần thử: {e}")
            return None


# ============================================================
# PROCESS CHUNK RESULT & VERIFY EVIDENCE
# ============================================================
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


# ============================================================
# RETRY FAILED CHUNKS
# ============================================================
def retry_failed_chunks(
    failed_chunks: List[List[Dict[str, Any]]],
    api_manager: GeminiRoundRobin,
    checkpoint: Dict[str, Dict[str, Any]],
    clean_results: List[Dict[str, Any]],
    system_prompt: str,
    max_retries: int,
    rpm_delay: float,
) -> None:
    """Thử lại các chunk thất bại sau khi hoàn tất vòng lặp chính."""
    if not failed_chunks:
        return

    print(f"\n[RETRY] Bắt đầu thử lại {len(failed_chunks)} chunk(s) thất bại...")
    remaining_failed: List[List[Dict[str, Any]]] = []

    for retry_idx, chunk in enumerate(failed_chunks, 1):
        label = f"Retry {retry_idx}/{len(failed_chunks)}"
        pending = [
            a for a in chunk
            if str(a.get("listing_id") or a.get("id")) not in checkpoint
        ]

        if not pending:
            print(f"[SKIP] [{label}] Toàn bộ bài đã có trong checkpoint.")
            continue

        print(f"[RETRY] [{label}] Đang chạy lại {len(pending)} bài...")
        parsed = call_gemini_chunk(
            api_manager=api_manager,
            chunk=pending,
            system_prompt=system_prompt,
            max_retries=max_retries,
            rpm_delay=rpm_delay,
        )

        if parsed is None:
            print(f"  [LOI] [{label}] Vẫn thất bại: {[str(a.get('listing_id') or a.get('id')) for a in pending]}")
            remaining_failed.append(pending)
        else:
            process_chunk_result(
                parsed=parsed,
                chunk=pending,
                checkpoint=checkpoint,
                clean_results=clean_results,
                chunk_label=label,
            )

        if retry_idx < len(failed_chunks):
            time.sleep(rpm_delay)

    failed_chunks.clear()
    failed_chunks.extend(remaining_failed)


# ============================================================
# MAIN PIPELINE
# ============================================================
def run_pipeline_chunking(
    datas: List[Dict[str, Any]],
    api_keys: List[str],
    model_name: str = DEFAULT_MODEL,
    rpm_delay: float = DEFAULT_RPM_DELAY,
    max_retries: int = DEFAULT_MAX_RETRIES,
    system_prompt: str = SYSTEM_PROMPT,
    checkpoint_path: Optional[Path] = None,
    max_tokens_per_chunk: int = DEFAULT_MAX_TOKENS_PER_CHUNK,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Main pipeline trích xuất thông tin qua LLM có hỗ trợ Dynamic Chunking & Checkpoint phục hồi.
    """
    if not datas:
        print("[PIPELINE] Không có dữ liệu đầu vào.")
        return [], []

    # 1. Khởi tạo API Manager
    api_manager = GeminiRoundRobin(
        api_keys=api_keys,
        model_name=model_name,
    )

    # 2. Tải Checkpoint cũ
    checkpoint, clean_results, metadata, completed_chunk_indices = load_checkpoint(checkpoint_path)

    # 3. Tạo Dynamic Chunks
    chunks = create_dynamic_chunks(
        datas,
        max_tokens_per_chunk=max_tokens_per_chunk,
        model_name=model_name,
    )

    total_chunks = len(chunks)
    print("=" * 65)
    print(
        f"[PIPELINE] TỔNG QUAN:\n"
        f"  - Tổng số bài: {len(datas)} bài\n"
        f"  - Số chunk động: {total_chunks} chunks\n"
        f"  - Model: {model_name} | {len(api_keys)} API keys\n"
        f"  - Đã xong từ trước: {len(checkpoint)} bài "
        f"({len(completed_chunk_indices)} chunks đã hoàn tất)"
    )
    print("=" * 65)

    failed_chunks: List[List[Dict[str, Any]]] = []

    # 4. Vòng lặp chính xử lý từng Chunk
    for idx, chunk in enumerate(chunks, 1):
        label = f"Chunk {idx}/{total_chunks}"

        # Kiểm tra nếu tất cả bài trong chunk đã được xử lý
        pending = [
            a for a in chunk
            if str(a.get("listing_id") or a.get("id")) not in checkpoint
        ]

        if not pending:
            # Chunk này đã xong toàn bộ -> bỏ qua tức thì KHÔNG time.sleep
            completed_chunk_indices.add(idx)
            continue

        print(f"\n[RUN] [{label}] Xử lý {len(pending)} bài (bỏ qua {len(chunk) - len(pending)} bài cũ)...")

        process_one_chunk(
            chunk=pending,
            chunk_label=label,
            api_manager=api_manager,
            checkpoint=checkpoint,
            clean_results=clean_results,
            failed_chunks=failed_chunks,
            system_prompt=system_prompt,
            max_retries=max_retries,
            rpm_delay=rpm_delay,
        )

        completed_chunk_indices.add(idx)

        # Cập nhật metadata tiến độ vào Checkpoint
        current_meta = {
            "last_processed_chunk": idx,
            "total_chunks": total_chunks,
            "completed_chunk_count": len(completed_chunk_indices),
            "completed_chunk_indices": sorted(list(completed_chunk_indices)),
            "total_listings": len(datas),
            "processed_listings_count": len(clean_results),
            "updated_at": datetime.now().isoformat(),
            "model_name": model_name,
        }

        save_checkpoint(
            checkpoint_path,
            clean_results,
            metadata=current_meta,
            failed_chunks=failed_chunks,
        )

        if idx < total_chunks:
            time.sleep(rpm_delay)

    # 5. Retry các chunk thất bại
    retry_failed_chunks(
        failed_chunks=failed_chunks,
        api_manager=api_manager,
        checkpoint=checkpoint,
        clean_results=clean_results,
        system_prompt=system_prompt,
        max_retries=max_retries,
        rpm_delay=rpm_delay,
    )

    # 6. Tổng kết bài lỗi
    total_failed = [
        a
        for chunk in failed_chunks
        for a in chunk
        if str(a.get("listing_id") or a.get("id")) not in checkpoint
    ]
    unique_failed = {str(a.get("listing_id") or a.get("id")): a for a in total_failed}
    total_failed_list = list(unique_failed.values())

    # 7. Báo cáo kết quả
    print("\n" + "=" * 65)
    print(
        f"[HOÀN TẤT] {len(checkpoint)}/{len(datas)} bài thành công"
        + (
            f" | {len(total_failed_list)} bài cần xử lý thủ công"
            if total_failed_list
            else " | 100% dữ liệu đã trích xuất sạch sẽ"
        )
    )
    print("=" * 65)

    # 8. Lưu Checkpoint lần cuối
    final_meta = {
        "last_processed_chunk": total_chunks,
        "total_chunks": total_chunks,
        "completed_chunk_count": len(completed_chunk_indices),
        "completed_chunk_indices": sorted(list(completed_chunk_indices)),
        "total_listings": len(datas),
        "processed_listings_count": len(clean_results),
        "updated_at": datetime.now().isoformat(),
        "model_name": model_name,
        "status": "COMPLETED" if not total_failed_list else "PARTIAL",
    }
    save_checkpoint(
        checkpoint_path,
        clean_results,
        metadata=final_meta,
        failed_chunks=failed_chunks,
    )

    return clean_results, total_failed_list