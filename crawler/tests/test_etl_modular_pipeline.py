"""Black-box unit & integration tests cho luồng ETL tách module qua file trung gian JSONL."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crawler.etl.io_utils import read_jsonl, restore_record_datetimes, write_jsonl
from crawler.etl.transform import ListingTransformer


# ---------------------------------------------------------------------------
# Nhóm 1: Happy Path (Roundtrip JSONL & Transform -> Intermediate -> Restore)
# ---------------------------------------------------------------------------

def test_jsonl_roundtrip_preserves_utf8_datetimes_and_vectors(tmp_path: Path):
    """write_jsonl -> read_jsonl -> restore_record_datetimes giữ nguyên tiếng Việt, vector và datetime."""
    now = datetime(2026, 11, 17, 10, 30, 0, tzinfo=timezone.utc)
    records = [
        {
            "listing_id": "nhatot_1001",
            "title": "Ký túc xá cao cấp Thủ Đức",
            "price_vnd": 850_000,
            "room_type": "SLEEPBOX",
            "furnishing_code": 1,
            "crawled_at": now,
            "posted_date": now,
            "last_checked_at": None,
            "vector": [0.125, -0.5, 0.875],
        }
    ]

    out_file = write_jsonl(tmp_path / "nested" / "listings_transformed.jsonl", records)
    assert out_file.exists()

    loaded = read_jsonl(out_file)
    assert len(loaded) == 1
    assert loaded[0]["title"] == "Ký túc xá cao cấp Thủ Đức"
    assert loaded[0]["vector"] == [0.125, -0.5, 0.875]

    restored = restore_record_datetimes(loaded[0])
    assert isinstance(restored["crawled_at"], datetime)
    assert isinstance(restored["posted_date"], datetime)
    assert restored["crawled_at"] == now
    assert restored["last_checked_at"] is None


def test_modular_transform_to_intermediate_preserves_rules_before_load(tmp_path: Path):
    """Transform -> ghi file trung gian -> đọc lại chuẩn bị cho Load giữ nguyên các rule chuẩn hóa."""
    raw_records = [
        {
            "listing_id": "nhatot_2001",
            "source": "nhatot",
            "title": "Giường tầng sinh viên gần Bách Khoa",
            "description": "Có sẵn giường, tủ đồ, máy lạnh.",
            "price_vnd": 900_000,
            "area_m2": 18.0,
            "city": "TP.HCM",
            "district": "Quận 10",
            "furnishing_code": None,
            "room_type": "ROOM",
            "is_active": True,
        }
    ]
    reports = {
        "nhatot_2001": {
            "room_type": "ROOM",
            "amenities": {"furniture": {"value": "yes", "evidence": "Có sẵn giường, tủ đồ"}},
        }
    }

    cleans = ListingTransformer(llm_reports=reports).transform(raw_records)
    assert len(cleans) == 1

    intermediate = write_jsonl(tmp_path / "listings_transformed.jsonl", cleans)
    reloaded = [restore_record_datetimes(r) for r in read_jsonl(intermediate)]

    assert len(reloaded) == 1
    assert reloaded[0]["furnishing_code"] == 2
    assert reloaded[0]["room_type"] == "SLEEPBOX"
    assert reloaded[0]["room_type_id"] == 4
    assert isinstance(reloaded[0]["crawled_at"], datetime)


# ---------------------------------------------------------------------------
# Nhóm 2: Boundary & Edge Cases
# ---------------------------------------------------------------------------

def test_read_jsonl_raises_on_missing_file_and_handles_empty_file(tmp_path: Path):
    """Đọc file không tồn tại phải báo FileNotFoundError; file rỗng trả về []."""
    with pytest.raises(FileNotFoundError):
        read_jsonl(tmp_path / "not_exists.jsonl")

    empty_file = tmp_path / "empty.jsonl"
    empty_file.write_text("\n  \n", encoding="utf-8")
    assert read_jsonl(empty_file) == []


def test_read_jsonl_raises_value_error_on_corrupt_json(tmp_path: Path):
    """Dòng JSON hỏng phải báo ValueError rõ ràng kèm số dòng."""
    bad_file = tmp_path / "bad.jsonl"
    bad_file.write_text('{"listing_id": "1"}\n{broken_json\n', encoding="utf-8")
    with pytest.raises(ValueError, match=":2:"):
        read_jsonl(bad_file)


# ---------------------------------------------------------------------------
# Nhóm 3: State Mutation
# ---------------------------------------------------------------------------

def test_restore_record_datetimes_does_not_mutate_input():
    """restore_record_datetimes trả bản sao mới, không sửa đổi dict đầu vào."""
    raw = {"listing_id": "1", "crawled_at": "2026-11-17T10:00:00"}
    snapshot = copy.deepcopy(raw)
    restored = restore_record_datetimes(raw)

    assert raw == snapshot
    assert isinstance(raw["crawled_at"], str)
    assert isinstance(restored["crawled_at"], datetime)
