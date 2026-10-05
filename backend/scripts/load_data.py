"""Load crawler data into PostgreSQL.

The processed CSV is the default source because it contains normalized
location IDs and poster information. Existing rows are updated by listing ID.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Base, SessionLocal, engine
from app.models import City, District, Listing, ListingEmbedding, RoomType, User, Ward


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "app" / "datas"


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _int(value: Any) -> int | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _float(value: Any) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _bool(value: Any) -> bool | None:
    text = _text(value)
    if text is None:
        return None
    return text.lower() in {"true", "1", "yes", "y", "t"}


def _datetime(value: Any) -> datetime | None:
    text = _text(value)
    if text is None:
        return None
    try:
        timestamp = float(text)
        if abs(timestamp) > 100_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp)
    except (ValueError, OverflowError, OSError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _images(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    text = _text(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, list):
                return [str(item) for item in parsed if item]
        except (SyntaxError, ValueError):
            pass
    return [item for item in text.split("|") if item]


def _upsert_location(session: Session, row: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    region_id = _int(row.get("region_id"))
    district_id = _int(row.get("district_id"))
    ward_id = _int(row.get("ward_id"))
    city_name = _text(row.get("city"))
    district_name = _text(row.get("district"))
    ward_name = _text(row.get("ward"))

    city = None
    if city_name:
        city = session.query(City).filter(City.name == city_name).one_or_none()
        if city is None:
            city = City(name=city_name)
            session.add(city)
            session.flush()
        else:
            city.name = city_name

    district = None
    ward = None
    if district_name:
        district_query = session.query(District).filter(District.name == district_name)
        if city is not None:
            district_query = district_query.filter(District.city_id == city.id)
        district = district_query.order_by(District.id).first()
        if district is None:
            if city is None:
                raise ValueError(f"District {district_id} has no city {region_id}")
            district = District(
                city_id=city.id,
                name=district_name,
            )
            session.add(district)
            session.flush()
        else:
            district.name = district_name
            if city is not None:
                district.city_id = city.id

    if ward_name:
        ward_query = session.query(Ward).filter(Ward.name == ward_name)
        if district is not None:
            ward_query = ward_query.filter(Ward.district_id == district.id)
        ward = ward_query.order_by(Ward.id).first()
        if ward is None:
            if district is None:
                raise ValueError(f"Ward {ward_id} has no district {district_id}")
            ward = Ward(
                district_id=district.id,
                name=ward_name,
            )
            session.add(ward)
            session.flush()
        else:
            ward.name = ward_name
            if district is not None:
                ward.district_id = district.id

    return (
        city.id if city else None,
        district.id if district else None,
        ward.id if ward else None,
    )


def _upsert_room_type(session: Session, value: Any) -> int | None:
    name = _text(value)
    if not name:
        return None
    room_type = session.query(RoomType).filter(RoomType.room_type == name).one_or_none()
    if room_type is None:
        room_type = RoomType(room_type=name)
        session.add(room_type)
        session.flush()
    return room_type.id


def _upsert_user(
    session: Session,
    row: dict[str, Any],
    cache: dict[str, User],
) -> str | None:
    poster_id = _text(row.get("poster_id"))
    if not poster_id:
        return None
    user = cache.get(poster_id)
    if user is None:
        user = session.get(User, poster_id)
    if user is None:
        user = User(id=poster_id, name=_text(row.get("poster_name")) or "Người đăng")
        session.add(user)
    cache[poster_id] = user
    user.name = _text(row.get("poster_name")) or user.name
    user.avatar_url = _text(row.get("poster_avatar"))
    user.live_ads = _int(row.get("poster_live_ads")) or 0
    user.sold_ads = _int(row.get("poster_sold_ads")) or 0
    user.is_company = _bool(row.get("is_company_ad"))
    return poster_id


def _listing_values(
    session: Session,
    row: dict[str, Any],
    user_cache: dict[str, User],
) -> dict[str, Any]:
    listing_id = _text(row.get("listing_id"))
    if not listing_id:
        raise ValueError("Missing listing_id")
    city_id, district_id, ward_id = _upsert_location(session, row)
    return {
        "id": listing_id,
        "source": _text(row.get("source")) or "nhatot",
        "url": _text(row.get("url")),
        "title": _text(row.get("title")) or "Untitled",
        "description": _text(row.get("description")),
        "price_string": _text(row.get("price_string")),
        "images": _images(row.get("images")),
        "main_image": _text(row.get("main_image")),
        "address_raw": _text(row.get("address_raw")),
        "price_vnd": _float(row.get("price_vnd")),
        "area_m2": _float(row.get("area_m2")),
        "price_million_per_m2": _float(row.get("price_million_per_m2")),
        "deposit": _float(row.get("deposit")),
        "furnishing_code": _int(row.get("furnishing_code")),
        "lat": _float(row.get("lat")),
        "lng": _float(row.get("lng")),
        "posted_date": _datetime(row.get("posted_date")),
        "crawled_at": _datetime(row.get("crawled_at")),
        "safety_score": _float(row.get("safety_score")),
        "concept_scores": row.get("concept_scores"),
        "poster_id": _upsert_user(session, row, user_cache),
        "region_id": city_id,
        "district_id": district_id,
        "ward_id": ward_id,
        "room_type_id": _upsert_room_type(session, row.get("room_type")),
    }


def _read_csv(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def _read_json(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        value = json.load(file)
    if isinstance(value, dict):
        yield value
    elif isinstance(value, list):
        yield from (item for item in value if isinstance(item, dict))


def _read_datas_json(path: Path) -> Iterable[dict[str, Any]]:
    yield from _read_json(path)


def _load_embeddings(data_dir: Path, session: Session, model_name: str) -> int:
    mapping_path = data_dir / "listing_embedding_mapping.parquet"
    vectors_path = data_dir / "listing_embeddings.npy"
    if not mapping_path.exists() or not vectors_path.exists():
        return 0

    try:
        import numpy as np
        import pyarrow.parquet as parquet
    except ImportError as error:
        raise RuntimeError(
            "Loading embeddings requires numpy and pyarrow. "
            "Install backend requirements first."
        ) from error

    listing_ids = parquet.read_table(mapping_path, columns=["listing_id"])["listing_id"].to_pylist()
    vectors = np.load(vectors_path, mmap_mode="r")
    if len(listing_ids) != len(vectors):
        raise ValueError("Embedding mapping and vector array have different lengths")

    loaded = 0
    for listing_id, vector in zip(listing_ids, vectors):
        if session.get(Listing, listing_id) is None:
            continue
        values = vector.astype("float32", copy=False)
        embedding = (
            session.query(ListingEmbedding)
            .filter(
                ListingEmbedding.listing_id == listing_id,
                ListingEmbedding.model_name == model_name,
            )
            .one_or_none()
        )
        if embedding is None:
            embedding = ListingEmbedding(
                listing_id=listing_id,
                model_name=model_name,
                dimension=int(values.shape[0]),
                vector=values.tolist(),
                content_hash=hashlib.sha256(values.tobytes()).hexdigest(),
            )
            session.add(embedding)
        else:
            embedding.dimension = int(values.shape[0])
            embedding.vector = values.tolist()
            embedding.content_hash = hashlib.sha256(values.tobytes()).hexdigest()
        loaded += 1
        if loaded % 500 == 0:
            session.commit()
    return loaded


def load_data(
    data_dir: Path = DEFAULT_DATA_DIR,
    embedding_model: str = "precomputed-768",
) -> tuple[int, int]:
    """Upsert listings and bundled embeddings; return (listing_count, embedding_count)."""
    datas_json_path = data_dir / "datas.json"
    if not datas_json_path.exists():
        raise FileNotFoundError(f"Data file {datas_json_path} does not exist")
    
    rows = _read_datas_json(data_dir / "datas.json")

    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    count = 0
    user_cache: dict[str, User] = {}
    try:
        for row in rows:
            values = _listing_values(session, row, user_cache)
            listing = session.get(Listing, values["id"])
            if listing is None:
                listing = Listing(**values)
                session.add(listing)
            else:
                for key, value in values.items():
                    setattr(listing, key, value)
            count += 1
            if count % 500 == 0:
                session.commit()
        session.commit()
        embedding_count = _load_embeddings(data_dir, session, embedding_model)
        session.commit()
        return count, embedding_count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load crawler data into PostgreSQL")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--embedding-model", default="precomputed-768")
    args = parser.parse_args()
    listing_count, embedding_count = load_data(args.data_dir, args.embedding_model)
    print(
        f"Loaded {listing_count} listings and {embedding_count} embeddings "
    )


if __name__ == "__main__":
    main()
