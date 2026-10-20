"""Unit tests for crawler/model/run_pipeline_chunking.py (checkpoint and processing)."""
import json
import pytest
from pathlib import Path
from crawler.model.llm import (
    load_checkpoint,
    save_checkpoint,
    convert_checkpoint_to_jsonl,
    process_chunk_result,
    is_quota_error,
)
from crawler.schema.listing import (
    ChunkExtractionWrapper,
    SingleListingExtraction,
    ListingExtraction,
    Amenities,
    Signal,
)


def test_is_quota_error():
    assert is_quota_error(Exception("429 Too Many Requests"))
    assert is_quota_error(Exception("Resource Exhausted"))
    assert is_quota_error(Exception("Rate limit reached"))
    assert not is_quota_error(Exception("Connection refused"))


def test_save_and_load_checkpoint_new_format(tmp_path: Path):
    ckpt_path = tmp_path / "checkpoint.json"

    clean_results = [
        {"listing_id": "1", "report": {"amenity_overall_score": 0.8}},
        {"listing_id": "2", "report": {"amenity_overall_score": 0.5}},
    ]
    metadata = {
        "last_processed_chunk": 2,
        "total_chunks": 5,
        "completed_chunk_count": 2,
        "completed_chunk_indices": [1, 2],
    }

    save_checkpoint(ckpt_path, clean_results, metadata=metadata)
    assert ckpt_path.exists()

    checkpoint, loaded_results, loaded_meta, completed_chunks = load_checkpoint(ckpt_path)

    assert len(checkpoint) == 2
    assert "1" in checkpoint
    assert "2" in checkpoint
    assert len(loaded_results) == 2
    assert loaded_meta["last_processed_chunk"] == 2
    assert loaded_meta["total_chunks"] == 5
    assert completed_chunks == {1, 2}


def test_load_checkpoint_legacy_list_format(tmp_path: Path):
    ckpt_path = tmp_path / "legacy_checkpoint.json"
    legacy_data = [
        {"listing_id": "100", "report": {"amenity_overall_score": 0.9}},
        {"listing_id": "101", "report": {"amenity_overall_score": 0.3}},
    ]
    ckpt_path.write_text(json.dumps(legacy_data), encoding="utf-8")

    checkpoint, loaded_results, loaded_meta, completed_chunks = load_checkpoint(ckpt_path)

    assert len(checkpoint) == 2
    assert "100" in checkpoint
    assert "101" in checkpoint
    assert len(loaded_results) == 2


def test_save_and_load_checkpoint_jsonl_format(tmp_path: Path):
    ckpt_path = tmp_path / "checkpoint.jsonl"

    clean_results = [
        {"listing_id": "item_1", "report": {"amenity_overall_score": 0.85}},
        {"listing_id": "item_2", "report": {"amenity_overall_score": 0.40}},
    ]
    metadata = {
        "last_processed_chunk": 3,
        "total_chunks": 10,
        "completed_chunk_count": 3,
        "completed_chunk_indices": [1, 2, 3],
    }

    save_checkpoint(ckpt_path, clean_results, metadata=metadata)
    assert ckpt_path.exists()

    checkpoint, loaded_results, loaded_meta, completed_chunks = load_checkpoint(ckpt_path)

    assert len(checkpoint) == 2
    assert "item_1" in checkpoint
    assert "item_2" in checkpoint
    assert len(loaded_results) == 2
    assert loaded_meta["last_processed_chunk"] == 3
    assert loaded_meta["total_chunks"] == 10
    assert completed_chunks == {1, 2, 3}


def test_convert_checkpoint_to_jsonl(tmp_path: Path):
    json_path = tmp_path / "checkpoint.json"
    clean_results = [
        {"listing_id": "conv_1", "report": {"amenity_overall_score": 0.70}},
    ]
    metadata = {"last_processed_chunk": 1, "total_chunks": 1}
    save_checkpoint(json_path, clean_results, metadata=metadata)

    jsonl_path = convert_checkpoint_to_jsonl(json_path)
    assert jsonl_path.exists()
    assert jsonl_path.suffix == ".jsonl"

    checkpoint, loaded_results, loaded_meta, _ = load_checkpoint(jsonl_path)
    assert len(checkpoint) == 1
    assert "conv_1" in checkpoint
    assert loaded_meta["last_processed_chunk"] == 1


def test_process_chunk_result_verification():
    chunk = [
        {"listing_id": "1", "text": "Phòng có máy lạnh Daikin, WC riêng."},
        {"listing_id": "2", "text": "Phòng giá rẻ 2tr."},
    ]

    # Report 1 has valid aircon evidence, but hallucinated mezzanine
    report1 = ListingExtraction(
        amenities=Amenities(
            aircon=Signal(value="yes", evidence="máy lạnh"),
            mezzanine=Signal(value="yes", evidence="gác lửng"),  # Hallucinated!
            private_wc=Signal(value="yes", evidence="WC riêng"),
        )
    )

    parsed = ChunkExtractionWrapper(
        reports=[
            SingleListingExtraction(id="1", report=report1),
        ]
    )

    checkpoint = {}
    clean_results = []

    newly_ids = process_chunk_result(
        parsed=parsed,
        chunk=chunk,
        checkpoint=checkpoint,
        clean_results=clean_results,
        chunk_label="Chunk 1/1",
    )

    assert newly_ids == {"1"}
    assert "1" in checkpoint
    res_report = checkpoint["1"]["report"]

    # aircon kept, mezzanine downgraded to unknown
    assert res_report["amenities"]["aircon"]["value"] == "yes"
    assert res_report["amenities"]["mezzanine"]["value"] == "unknown"
    assert res_report["amenities"]["private_wc"]["value"] == "yes"

    # Precalculated scores attached
    assert "amenity_overall_score" in res_report
    assert "safety_score" in res_report
    assert "concept_scores" in res_report
    # private_wc (20) + aircon (20) = 40 pts -> 0.40
    assert res_report["amenity_overall_score"] == 0.40


def test_crawler_model_llm_exports():
    import crawler.model.llm as llm
    assert hasattr(llm, "run_pipeline_chunking")
    assert hasattr(llm, "load_checkpoint")
    assert hasattr(llm, "save_checkpoint")
    assert hasattr(llm, "create_dynamic_chunks")
    assert hasattr(llm, "GeminiRoundRobin")
    assert hasattr(llm, "SYSTEM_PROMPT")


def test_create_dynamic_chunks():
    from crawler.model.llm import create_dynamic_chunks
    articles = [
        {"listing_id": "1", "text": "Phòng trọ 1 giá rẻ"},
        {"listing_id": "2", "text": "Phòng trọ 2 đầy đủ tiện nghi"},
    ]
    chunks = create_dynamic_chunks(articles, max_tokens_per_chunk=1000)
    assert len(chunks) == 1
    assert len(chunks[0]) == 2

