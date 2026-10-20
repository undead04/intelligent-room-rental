import os
import sys
import hashlib
from pathlib import Path
from collections import Counter
from sqlalchemy import text

# Đảm bảo root dự án có trong sys.path khi chạy file độc lập
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from crawler.schema.enums import CANONICAL_ROOM_TYPES, ROOM_TYPE_CODE_TO_ID
from crawler.config.settings import DEFAULT_EMBEDDING_MODEL
from crawler.etl.db_models import (
    Base,
    City,
    District,
    Listing,
    ListingEmbedding,
    RoomType,
    User,
    Ward,
    create_db_session,
)


class DataLoader:
    """
    [LOAD STAGE]
    Chịu trách nhiệm lưu trữ và nạp dữ liệu sạch vào các đích đến (Destinations):
    Nạp trực tiếp vào CSDL PostgreSQL (pgvector).
    """

    def __init__(self):
        pass

    def load_to_postgres(self, records: list[dict], db_url: str = None) -> tuple[int, int]:
        """Nạp trực tiếp dữ liệu phòng và vector embedding vào PostgreSQL (pgvector).
        Tự động upsert City, District, Ward, RoomType, User, Listing, ListingEmbedding.
        """
        if not records:
            print("[LOAD] Không có bản ghi nào để nạp vào PostgreSQL.", flush=True)
            return 0, 0

        # Đảm bảo pgvector extension và bảng dữ liệu được khởi tạo độc lập
        engine, session = create_db_session(db_url)
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.execute(text("ALTER TABLE room_types ADD COLUMN IF NOT EXISTS code VARCHAR(50);"))
            conn.commit()
        Base.metadata.create_all(bind=engine)

        def _sync_sequence(table_name: str, id_col: str = "id"):
            try:
                session.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}', '{id_col}'), "
                        f"COALESCE((SELECT MAX({id_col}) FROM {table_name}), 0) + 1, false);"
                    )
                )
            except Exception:
                pass

        # Đồng bộ sequence lúc bắt đầu
        for tbl in ("cities", "districts", "wards", "room_types"):
            _sync_sequence(tbl)

        # Khởi tạo / cập nhật 5 loại phòng chuẩn canonical (ID: 1..5)
        for code, (cid, label) in CANONICAL_ROOM_TYPES.items():
            rt_obj = session.get(RoomType, cid)
            if rt_obj is None:
                rt_obj = RoomType(id=cid, code=code, name=label)
                session.add(rt_obj)
            else:
                rt_obj.code = code
                rt_obj.name = label
        session.flush()
        _sync_sequence("room_types")

        user_cache: dict[str, User] = {}
        city_cache: dict[str, City] = {}
        district_cache: dict[tuple[int, str], District] = {}
        ward_cache: dict[tuple[int, str], Ward] = {}

        listing_count = 0
        embedding_count = 0

        print(f"\n[LOAD] Bắt đầu nạp {len(records)} bản ghi vào PostgreSQL...", flush=True)

        try:
            for r in records:
                lid = str(r.get("listing_id") or r.get("id") or "").strip()
                if not lid:
                    continue

                # 1. Địa lý: City -> District -> Ward
                c_name = str(r.get("city") or "").strip()
                c_id = r.get("region_id") or r.get("city_id")
                city_obj = None
                if c_name:
                    if c_name not in city_cache:
                        city_obj = session.query(City).filter(City.name == c_name).first()
                        if city_obj is None:
                            safe_id = c_id if (isinstance(c_id, int) and c_id > 0 and session.get(City, c_id) is None) else None
                            city_obj = City(id=safe_id, name=c_name) if safe_id else City(name=c_name)
                            session.add(city_obj)
                            session.flush()
                            _sync_sequence("cities")
                        city_cache[c_name] = city_obj
                    else:
                        city_obj = city_cache[c_name]

                d_name = str(r.get("district") or "").strip()
                d_id = r.get("district_id")
                dist_obj = None
                if d_name and city_obj:
                    key = (city_obj.id, d_name)
                    if key not in district_cache:
                        dist_obj = session.query(District).filter(
                            District.name == d_name,
                            District.city_id == city_obj.id,
                        ).first()
                        if dist_obj is None:
                            safe_id = d_id if (isinstance(d_id, int) and d_id > 0 and session.get(District, d_id) is None) else None
                            dist_obj = District(id=safe_id, city_id=city_obj.id, name=d_name) if safe_id else District(city_id=city_obj.id, name=d_name)
                            session.add(dist_obj)
                            session.flush()
                            _sync_sequence("districts")
                        district_cache[key] = dist_obj
                    else:
                        dist_obj = district_cache[key]

                w_name = str(r.get("ward") or "").strip()
                w_id = r.get("ward_id")
                ward_obj = None
                if w_name and dist_obj:
                    key = (dist_obj.id, w_name)
                    if key not in ward_cache:
                        ward_obj = session.query(Ward).filter(
                            Ward.name == w_name,
                            Ward.district_id == dist_obj.id,
                        ).first()
                        if ward_obj is None:
                            safe_id = w_id if (isinstance(w_id, int) and w_id > 0 and session.get(Ward, w_id) is None) else None
                            ward_obj = Ward(id=safe_id, district_id=dist_obj.id, name=w_name) if safe_id else Ward(district_id=dist_obj.id, name=w_name)
                            session.add(ward_obj)
                            session.flush()
                            _sync_sequence("wards")
                        ward_cache[key] = ward_obj
                    else:
                        ward_obj = ward_cache[key]

                # 2. Room Type Mapping (Decoupled completely from external category_id)
                rt_id = r.get("room_type_id")
                if not isinstance(rt_id, int) or rt_id not in (1, 2, 3, 4, 5):
                    rt_code = str(r.get("room_type") or "").strip().upper()
                    rt_id = ROOM_TYPE_CODE_TO_ID.get(rt_code, 1)

                # 3. User (Poster) Upsert
                poster_id = r.get("poster_id")
                if poster_id:
                    poster_id = str(poster_id)
                    if poster_id not in user_cache:
                        user_obj = session.get(User, poster_id)
                        if user_obj is None:
                            user_obj = User(
                                id=poster_id,
                                name=str(r.get("poster_name") or "Người đăng"),
                                avatar_url=r.get("poster_avatar"),
                                live_ads=int(r.get("poster_live_ads") or 0),
                                sold_ads=int(r.get("poster_sold_ads") or 0),
                                is_company=bool(r.get("is_company_ad")),
                            )
                            session.add(user_obj)
                            session.flush()
                        user_cache[poster_id] = user_obj

                # 4. Listing Upsert
                listing_vals = {
                    "id": lid,
                    "source": r.get("source") or "nhatot",
                    "url": r.get("url"),
                    "title": r.get("title") or "Untitled",
                    "description": r.get("description"),
                    "price_string": r.get("price_string"),
                    "main_image": r.get("main_image"),
                    "images": r.get("images") if isinstance(r.get("images"), list) else [],
                    "price_vnd": r.get("price_vnd"),
                    "area_m2": r.get("area_m2"),
                    "price_million_per_m2": r.get("price_million_per_m2"),
                    "deposit": r.get("deposit"),
                    "furnishing_code": r.get("furnishing_code"),
                    "address_raw": r.get("address_raw"),
                    "lat": r.get("lat"),
                    "lng": r.get("lng"),
                    "posted_date": r.get("posted_date"),
                    "crawled_at": r.get("crawled_at"),
                    "safety_score": r.get("safety_score"),
                    "concept_scores": r.get("concept_scores"),
                    "amenity_overall": r.get("amenity_overall"),
                    "price_score": r.get("price_score"),
                    "poster_id": poster_id,
                    "region_id": city_obj.id if city_obj else None,
                    "district_id": dist_obj.id if dist_obj else None,
                    "ward_id": ward_obj.id if ward_obj else None,
                    "room_type_id": rt_id,
                }

                existing_listing = session.get(Listing, lid)
                if existing_listing is None:
                    session.add(Listing(**listing_vals))
                else:
                    for k, v in listing_vals.items():
                        setattr(existing_listing, k, v)
                listing_count += 1

                # 5. ListingEmbedding Upsert (lưu vector 768 chiều vào PostgreSQL)
                vec = r.get("vector")
                if vec:
                    model_name = str(r.get("embedding_model") or DEFAULT_EMBEDDING_MODEL)
                    dim = int(r.get("embedding_dim") or len(vec))
                    vec_list = list(vec) if not isinstance(vec, list) else vec
                    content_hash = hashlib.sha256(str(vec_list[:10]).encode("utf-8")).hexdigest()

                    emb_obj = (
                        session.query(ListingEmbedding)
                        .filter(
                            ListingEmbedding.listing_id == lid,
                            ListingEmbedding.model_name == model_name,
                        )
                        .one_or_none()
                    )

                    if emb_obj is None:
                        session.add(ListingEmbedding(
                            listing_id=lid,
                            model_name=model_name,
                            dimension=dim,
                            vector=vec_list,
                            content_hash=content_hash,
                        ))
                    else:
                        emb_obj.dimension = dim
                        emb_obj.vector = vec_list
                        emb_obj.content_hash = content_hash
                    embedding_count += 1

                if listing_count % 500 == 0:
                    session.commit()
                    print(f"  -> Đã nạp {listing_count}/{len(records)} tin vào PostgreSQL...", flush=True)

            session.commit()
            print(f"[LOAD] Nạp thành công: {listing_count} bài đăng và {embedding_count} vector vào PostgreSQL!", flush=True)
            return listing_count, embedding_count
        except Exception as e:
            session.rollback()
            print(f"[LOAD] Lỗi nạp PostgreSQL: {e}", flush=True)
            raise
        finally:
            session.close()

    def print_summary(self, records: list[dict]):
        """In báo cáo thống kê tóm tắt sau khi Load"""
        if not records:
            return

        total = len(records)
        active_count = sum(1 for r in records if r.get("is_active") is True or str(r.get("is_active")).lower() == "true")
        expired_count = total - active_count

        print("\n" + "=" * 55, flush=True)
        print("          BÁO CÁO TỔNG HỢP PIPELINE ETL", flush=True)
        print("=" * 55, flush=True)
        print(f"Tổng số tin đăng hợp lệ: {total}", flush=True)
        print(f"  - Tin đang hoạt động (Active): {active_count} ({active_count / total * 100:.1f}%)", flush=True)
        print(f"  - Tin đã hết hạn/ẩn (Expired): {expired_count} ({expired_count / total * 100:.1f}%)", flush=True)

        sources = Counter([r.get("source", "unknown") for r in records])
        print("\nPhân bố theo nguồn dữ liệu:", flush=True)
        for src, cnt in sources.items():
            print(f"  - {src}: {cnt} tin", flush=True)

        districts = [r.get("district") for r in records if r.get("district")]
        if districts:
            counts = Counter(districts)
            print("\nTop 10 khu vực nhiều phòng nhất:", flush=True)
            for dist, count in counts.most_common(10):
                print(f"  - {dist}: {count} tin", flush=True)
        print("=" * 55 + "\n", flush=True)


if __name__ == "__main__":
    import argparse
    from crawler.etl.extract import extract_raw_listings
    from crawler.etl.transform import ListingTransformer

    parser = argparse.ArgumentParser(description="Test nạp dữ liệu vào PostgreSQL")
    parser.add_argument("--limit", type=int, default=3, help="Số bản ghi test")
    args = parser.parse_args()

    raws = extract_raw_listings(limit=args.limit)
    if not raws:
        print("[LOAD] Không có dữ liệu thô trong Staging DB.")
    else:
        transformer = ListingTransformer()
        cleans = transformer.transform(raws)
        loader = DataLoader()
        try:
            counts = loader.load_to_postgres(cleans)
            loader.print_summary(cleans)
            print(f"[LOAD DEMO] Hoàn tất nạp dữ liệu: {counts[0]} tin, {counts[1]} vector.")
        except Exception as e:
            print(f"[LOAD DEMO] Không thể nạp PostgreSQL (CSDL có thể chưa chạy): {e}")
