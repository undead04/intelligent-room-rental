import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
try:
    from crawler.config.settings import GEMINI_API_KEY
    from crawler.model.llm.checkpoint import load_checkpoint, save_checkpoint
    from crawler.model.llm.chunker import create_dynamic_chunks
    from crawler.model.llm.client import (
        DEFAULT_MAX_RETRIES,
        DEFAULT_RPM_DELAY,
        GeminiRoundRobin,
        call_gemini_chunk,
    )
    from crawler.model.llm.processor import process_chunk_result, process_one_chunk
    from crawler.model.llm.prompt import SYSTEM_PROMPT
except ImportError:
    from config.settings import GEMINI_API_KEY
    from checkpoint import load_checkpoint, save_checkpoint
    from chunker import create_dynamic_chunks
    from client import (
        DEFAULT_MAX_RETRIES,
        DEFAULT_RPM_DELAY,
        GeminiRoundRobin,
        call_gemini_chunk,
    )
    from processor import process_chunk_result, process_one_chunk
    from prompt import SYSTEM_PROMPT


DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_MAX_TOKENS_PER_CHUNK = 2500


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


if __name__ == "__main__":
    import argparse
    import os
    from dotenv import load_dotenv
    from crawler.etl.extract import extract_raw_listings

    load_dotenv()

    parser = argparse.ArgumentParser(description="Chạy LLM Extraction Pipeline với Dynamic Chunking & Checkpoint")
    parser.add_argument("--limit", type=int, default=None, help="Giới hạn số lượng bài đăng cần trích xuất")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS_PER_CHUNK, help="Ngưỡng token tối đa mỗi chunk")
    parser.add_argument("--rpm-delay", type=float, default=DEFAULT_RPM_DELAY, help="Thời gian nghỉ giữa các request (giây)")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Tên model Gemini sử dụng")
    args = parser.parse_args()

    raw_keys = GEMINI_API_KEY
    keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
    if not keys:
        raise RuntimeError("Vui lòng cấu hình GEMINI_API_KEYS hoặc GEMINI_API_KEY trong file .env trước khi chạy LLM pipeline.")

    records = extract_raw_listings(limit=args.limit)
    run_pipeline_chunking(
        datas=records,
        api_keys=keys,
        model_name=args.model,
        rpm_delay=args.rpm_delay,
        max_tokens_per_chunk=args.max_tokens,
    )

