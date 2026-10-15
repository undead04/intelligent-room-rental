import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


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
