import os
import sys
import csv
from collections import Counter

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_PROCESSED_CSV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "processed", "listings_clean.csv"))
DEFAULT_PROCESSED_JSON = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "processed", "listings_clean.json"))

class DataLoader:
    """
    [LOAD STAGE]
    Chịu trách nhiệm lưu trữ và nạp dữ liệu sạch vào các đích đến (Destinations):
    1. CSV (`listings_clean.csv`) - Dùng cho phân tích nhanh, báo cáo
    2. JSON (`datas.json` / `listings_clean.json`) - Dùng cho backend & nạp CSDL
    3. Parquet - Dùng cho huấn luyện mô hình Machine Learning
    4. PostgreSQL / Database - Nạp vào CSDL hệ thống
    """

    def __init__(self):
        pass

    def load_to_json(self, records: list[dict], output_path: str = None) -> str:
        """Xuất danh sách records ra file JSON (chuẩn UTF-8, hỗ trợ datetime)"""
        target_path = output_path or DEFAULT_PROCESSED_JSON
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        if not records:
            print("[LOAD] Không có bản ghi nào để lưu ra JSON.", flush=True)
            return target_path

        import json

        def default_serializer(o):
            if hasattr(o, "isoformat"):
                return o.isoformat()
            if hasattr(o, "__dict__"):
                return o.__dict__
            return str(o)

        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2, default=default_serializer)

        print(f"[LOAD] Đã lưu thành công {len(records)} bản ghi vào JSON: {target_path}", flush=True)
        return target_path

    def load_to_csv(self, records: list[dict], output_path: str = None) -> str:
        """Xuất danh sách records ra file CSV (chuẩn UTF-8 BOM để Excel đọc không lỗi font)"""
        target_path = output_path or DEFAULT_PROCESSED_CSV
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        if not records:
            print("[LOAD] Không có bản ghi nào để lưu ra CSV.", flush=True)
            return target_path

        import json

        # Thu thập đầy đủ các cột dữ liệu
        fieldnames = list(records[0].keys())
        for r in records[1:]:
            for k in r.keys():
                if k not in fieldnames:
                    fieldnames.append(k)

        # Chuẩn hóa dict/list sang JSON string trước khi ghi CSV
        serialized_records = []
        for r in records:
            item = {}
            for k in fieldnames:
                val = r.get(k)
                if isinstance(val, (dict, list)):
                    item[k] = json.dumps(val, ensure_ascii=False)
                elif hasattr(val, "isoformat"):
                    item[k] = val.isoformat()
                else:
                    item[k] = val
            serialized_records.append(item)

        with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(serialized_records)

        print(f"[LOAD] Đã lưu thành công {len(records)} bản ghi vào CSV: {target_path}", flush=True)
        return target_path

    def load_to_parquet(self, records: list[dict], output_path: str = None) -> str:
        """
        Xuất danh sách records ra file Parquet (tối ưu nạp dữ liệu cho ML/XGBoost).
        Yêu cầu có pandas & pyarrow nếu máy hỗ trợ.
        """
        target_path = output_path or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "processed", "listings_clean.parquet"))
        try:
            import pandas as pd
            df = pd.DataFrame(records)
            df.to_parquet(target_path, index=False)
            print(f"[LOAD] Đã xuất thành công file Parquet: {target_path}", flush=True)
            return target_path
        except ImportError:
            print("[LOAD] Chưa cài đặt pyarrow/pandas. Bỏ qua xuất Parquet.", flush=True)
            return None
        except Exception as e:
            print(f"[LOAD] Lỗi xuất Parquet: {e}", flush=True)
            return None

    def load_to_postgres(self, records: list[dict], db_url: str = None) -> tuple[int, int]:
        """Nạp trực tiếp dữ liệu phòng và vector embedding vào PostgreSQL (pgvector).
        Tự động upsert City, District, Ward, RoomType, User, Listing, ListingEmbedding.
        """
        if not records:
            print("[LOAD] Không có bản ghi nào để nạp vào PostgreSQL.", flush=True)
            return 0, 0

        import hashlib
        import numpy as np
        from sqlalchemy import text
        try:
            from app.core.database import SessionLocal, engine, Base
            from app.models import City, District, Ward, RoomType, User, Listing, ListingEmbedding
            from app.core.config import settings
        except ImportError:
            from backend.app.core.database import SessionLocal, engine, Base
            from backend.app.models import City, District, Ward, RoomType, User, Listing, ListingEmbedding
            from backend.app.core.config import settings

        # Đảm bảo pgvector extension và bảng dữ liệu được khởi tạo
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
            conn.commit()
        Base.metadata.create_all(bind=engine)
        session = SessionLocal()

        # Fallback: Nếu records chưa có inline "vector", tự động kiểm tra file .npy/.parquet trong crawler/data/embeddings
        precomputed_vectors: dict[str, tuple[list[float], str, int]] = {}
        has_inline_vector = any("vector" in r and r["vector"] for r in records)
        if not has_inline_vector:
            emb_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "embeddings"))
            npy_path = os.path.join(emb_dir, "listing_embeddings.npy")
            map_path = os.path.join(emb_dir, "listing_embedding_mapping.parquet")
            if os.path.exists(npy_path) and os.path.exists(map_path):
                try:
                    import pandas as pd
                    vectors_arr = np.load(npy_path)
                    mapping_df = pd.read_parquet(map_path)
                    for _, row in mapping_df.iterrows():
                        idx = int(row["embedding_index"])
                        lid_key = str(row["id"]).strip()
                        m_name = str(row.get("model_name") or settings.EMBEDDING_MODEL_NAME)
                        dim_val = int(row.get("embedding_dim") or vectors_arr.shape[1])
                        precomputed_vectors[lid_key] = (vectors_arr[idx].astype(np.float32).tolist(), m_name, dim_val)
                    print(f"[LOAD] Đã tải {len(precomputed_vectors)} vector từ {emb_dir}", flush=True)
                except Exception as e:
                    print(f"[LOAD] Không thể đọc file embedding sẵn có ({e}), bỏ qua fallback.", flush=True)

        user_cache: dict[str, User] = {}
        city_cache: dict[str, City] = {}
        district_cache: dict[tuple[int, str], District] = {}
        ward_cache: dict[tuple[int, str], Ward] = {}
        room_type_cache: dict[int, RoomType] = {}

        listing_count = 0
        embedding_count = 0

        print(f"\n[LOAD] Bắt đầu nạp {len(records)} bản ghi vào PostgreSQL...", flush=True)

        try:
            for r in records:
                lid = str(r.get("listing_id") or r.get("id") or "").strip()
                if not lid:
                    continue

                # 1. Location Upsert
                reg_id = r.get("region_id")
                dist_id = r.get("district_id")
                w_id = r.get("ward_id")
                c_name = r.get("city")
                d_name = r.get("district")
                w_name = r.get("ward")

                city_obj = None
                if c_name:
                    if c_name not in city_cache:
                        city_obj = session.query(City).filter(City.name == c_name).first()
                        if city_obj is None:
                            city_obj = City(name=c_name, id=reg_id)
                            session.add(city_obj)
                            session.flush()
                        city_cache[c_name] = city_obj
                    else:
                        city_obj = city_cache[c_name]

                dist_obj = None
                if d_name and city_obj:
                    key = (city_obj.id, d_name)
                    if key not in district_cache:
                        dist_obj = session.query(District).filter(District.name == d_name, District.city_id == city_obj.id).first()
                        if dist_obj is None:
                            dist_obj = District(name=d_name, city_id=city_obj.id, id=dist_id)
                            session.add(dist_obj)
                            session.flush()
                        district_cache[key] = dist_obj
                    else:
                        dist_obj = district_cache[key]

                ward_obj = None
                if w_name and dist_obj:
                    key = (dist_obj.id, w_name)
                    if key not in ward_cache:
                        ward_obj = session.query(Ward).filter(Ward.name == w_name, Ward.district_id == dist_obj.id).first()
                        if ward_obj is None:
                            ward_obj = Ward(name=w_name, district_id=dist_obj.id, id=w_id)
                            session.add(ward_obj)
                            session.flush()
                        ward_cache[key] = ward_obj
                    else:
                        ward_obj = ward_cache[key]

                # 2. Room Type Upsert
                rt_name = r.get("room_type")
                cat_id = r.get("category_id") or r.get("room_type_id")
                rt_id = None
                if cat_id:
                    if cat_id not in room_type_cache:
                        rt_obj = session.query(RoomType).filter(RoomType.id == cat_id).first()
                        if rt_obj is None:
                            rt_obj = RoomType(id=cat_id, name=str(rt_name or "Phòng trọ"))
                            session.add(rt_obj)
                            session.flush()
                        room_type_cache[cat_id] = rt_obj
                    rt_id = cat_id

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

                # 5. ListingEmbedding Upsert (hỗ trợ cả inline vector từ ETL hoặc file .npy/.parquet từ crawler/data/embeddings)
                vec = r.get("vector")
                model_name = r.get("embedding_model") or settings.EMBEDDING_MODEL_NAME
                dim = r.get("embedding_dim") or (len(vec) if vec else None)

                if not vec and lid in precomputed_vectors:
                    vec, model_name, dim = precomputed_vectors[lid]

                if vec:
                    vec_bytes = np.array(vec, dtype=np.float32).tobytes()
                    content_hash = hashlib.sha256(vec_bytes).hexdigest()

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
                            vector=vec,
                            content_hash=content_hash,
                        ))
                    else:
                        emb_obj.dimension = dim
                        emb_obj.vector = vec
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
    import json

    parser = argparse.ArgumentParser(description="Nạp dữ liệu đã xử lý từ Crawler vào PostgreSQL (pgvector)")
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Đường dẫn file JSON đã qua ETL (mặc định: tự động tìm datas.json hoặc listings_clean.json trong crawler/data/processed/)",
    )
    args = parser.parse_args()

    processed_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "processed"))
    input_path = args.input
    if not input_path:
        datas_json = os.path.join(processed_dir, "datas.json")
        clean_json = os.path.join(processed_dir, "listings_clean.json")
        input_path = datas_json if os.path.exists(datas_json) else clean_json

    if not os.path.exists(input_path):
        print(f"[LOAD] Không tìm thấy file dữ liệu tại: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        records_data = json.load(f)

    loader = DataLoader()
    loader.load_to_postgres(records_data)
    loader.print_summary(records_data)

