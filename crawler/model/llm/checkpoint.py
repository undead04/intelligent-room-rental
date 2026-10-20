import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def load_checkpoint(
    checkpoint_path: Optional[Path],
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Set[int]]:
    """
    Tải checkpoint cũ và thông tin tiến độ đã chạy.
    Hỗ trợ linh hoạt:
    - Định dạng .jsonl (JSON Lines, streaming tốc độ cao)
    - Định dạng .json mới (object có metadata và results)
    - Định dạng .json cũ (array các dict)

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

    is_jsonl = str(checkpoint_path).endswith(".jsonl")

    # 1. Đọc file định dạng JSONL (tối ưu tốc độ cao)
    if is_jsonl:
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except Exception:
                        continue
                    if "__meta__" in record:
                        metadata.update(record["__meta__"])
                        completed_chunks = set(metadata.get("completed_chunk_indices", []))
                    elif "metadata" in record and len(record) == 1:
                        metadata.update(record["metadata"])
                        completed_chunks = set(metadata.get("completed_chunk_indices", []))
                    else:
                        listing_id = str(record.get("listing_id") or record.get("id"))
                        checkpoint[listing_id] = record
                        clean_results.append(record)
        except Exception as e:
            print(f"[CANH BAO] Không thể đọc checkpoint JSONL từ {checkpoint_path}: {e}")
            return checkpoint, clean_results, metadata, completed_chunks

        last_chunk = metadata.get("last_processed_chunk", len(completed_chunks))
        total_chunks = metadata.get("total_chunks", "?")
        print(
            f"[RESUME] Đã nạp {len(checkpoint)} bài từ checkpoint JSONL: {checkpoint_path}\n"
            f"         Tiến độ: Đã xong Chunk {last_chunk}/{total_chunks} "
            f"({len(completed_chunks)} chunks hoàn tất)"
        )
        return checkpoint, clean_results, metadata, completed_chunks

    # 2. Đọc file định dạng JSON truyền thống (kèm fallback sang JSONL nếu nội dung thực tế là JSONL)
    try:
        raw_text = checkpoint_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return checkpoint, clean_results, metadata, completed_chunks
        try:
            raw_data = json.loads(raw_text)
        except json.JSONDecodeError:
            # Fallback đọc theo dòng nếu file đuôi .json nhưng nội dung là JSONL
            for line in raw_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if "__meta__" in record:
                        metadata.update(record["__meta__"])
                    else:
                        listing_id = str(record.get("listing_id") or record.get("id"))
                        checkpoint[listing_id] = record
                        clean_results.append(record)
                except Exception:
                    continue
            completed_chunks = set(metadata.get("completed_chunk_indices", []))
            return checkpoint, clean_results, metadata, completed_chunks
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
    Tự động ghi theo:
    - .jsonl: dòng đầu là `__meta__`, các dòng sau là từng bản ghi JSON (nhẹ, nhanh, không tràn RAM)
    - .json: đối tượng JSON lồng nhau truyền thống
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

    meta_dict = dict(metadata or {})
    if failed_ids:
        meta_dict["failed_listing_ids"] = sorted(list(set(failed_ids)))

    tmp_path = checkpoint_path.with_suffix(f"{checkpoint_path.suffix}.tmp")
    is_jsonl = str(checkpoint_path).endswith(".jsonl")

    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            if is_jsonl:
                # Ghi JSON Lines
                if meta_dict:
                    f.write(json.dumps({"__meta__": meta_dict}, ensure_ascii=False) + "\n")
                for r in clean_results:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            else:
                # Ghi JSON truyền thống
                payload = {
                    "metadata": meta_dict,
                    "results": clean_results,
                    "failed_listing_ids": meta_dict.get("failed_listing_ids", []),
                }
                json.dump(payload, f, ensure_ascii=False, indent=2)

            f.flush()
            os.fsync(f.fileno())

        if tmp_path.exists():
            tmp_path.replace(checkpoint_path)
    except Exception as e:
        print(f"[LOI] Không thể lưu checkpoint: {e}")


def convert_checkpoint_to_jsonl(
    source_path: Path,
    target_path: Optional[Path] = None,
) -> Path:
    """Chuyển đổi một file checkpoint .json hiện có sang .jsonl để tăng tốc độ I/O."""
    source_path = Path(source_path)
    if not source_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file nguồn: {source_path}")

    dest_path = target_path or source_path.with_suffix(".jsonl")
    checkpoint, clean_results, metadata, completed_chunks = load_checkpoint(source_path)

    save_checkpoint(
        dest_path,
        clean_results=clean_results,
        metadata=metadata,
    )
    print(f"[CONVERT] Đã chuyển đổi thành công {len(clean_results)} bài sang JSONL: {dest_path}")
    return dest_path
