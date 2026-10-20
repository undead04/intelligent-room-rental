import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from crawler.config.settings import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS_PER_CHUNK,
    DEFAULT_RPM_DELAY,
    GEMINI_API_KEYS,
)
from crawler.model.llm.checkpoint import load_checkpoint, save_checkpoint
from crawler.model.llm.chunker import create_dynamic_chunks
from crawler.model.llm.client import GeminiRoundRobin
from crawler.model.llm.processor import process_one_chunk
from crawler.model.llm.prompt import SYSTEM_PROMPT


DEFAULT_MODEL = DEFAULT_GEMINI_MODEL


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
    chunks_to_retry = list(failed_chunks)
    failed_chunks.clear()

    for retry_idx, chunk in enumerate(chunks_to_retry, 1):
        label = f"Retry {retry_idx}/{len(chunks_to_retry)}"
        process_one_chunk(
            chunk=chunk,
            chunk_label=label,
            api_manager=api_manager,
            checkpoint=checkpoint,
            clean_results=clean_results,
            failed_chunks=failed_chunks,
            system_prompt=system_prompt,
            max_retries=max_retries,
            rpm_delay=rpm_delay,
        )
        if retry_idx < len(chunks_to_retry):
            time.sleep(rpm_delay)


def run_pipeline_chunking(
    datas: List[Dict[str, Any]],
    api_keys: List[str],
    model_name: str = DEFAULT_MODEL,
    rpm_delay: float = DEFAULT_RPM_DELAY,
    max_retries: int = DEFAULT_MAX_RETRIES,
    system_prompt: str = SYSTEM_PROMPT,
    checkpoint_path: Optional[Path] = None,
    max_tokens_per_chunk: int = DEFAULT_MAX_TOKENS_PER_CHUNK,
    max_items_per_chunk: int = 5,
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
        max_items_per_chunk=max_items_per_chunk,
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


