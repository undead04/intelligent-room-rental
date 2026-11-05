"""
ml/feature_extractor.py
Trích xuất đặc trưng (Feature Extraction) chuẩn hóa Toàn Quốc cho mô hình định giá phòng trọ ML (Homigo).

Đặc tả nâng cấp v2:
1. Phạm vi địa lý Toàn Quốc: Bounding Box bao phủ toàn lãnh thổ Việt Nam (lat [8.0, 23.5], lng [102.0, 110.0]).
2. Danh mục 17 đặc trưng nhị phân Canonical Taxonomy (10 Amenities + 3 Rules + 4 Safety).
3. Biến phân loại phân khúc phòng `room_type_id` (1: ROOM, 2: STUDIO, 3: APARTMENT, 4: SLEEPBOX, 5: WHOLE_HOUSE).
4. Điểm chất lượng ngữ nghĩa LLM: `amenity_overall` và `safety_score` (tự động fallback nội suy theo trọng số chuẩn nếu chưa có).
5. Khoảng cách Haversine vector hóa đến trung tâm đô thị (`dist_nearest_hub_km`) và cụm đại học lớn (`dist_nearest_uni_km`) trên cả nước.
6. Bộ lọc thích ứng theo loại phòng (Room-Type Adaptive Filtering): Bảo vệ phân khúc Ký túc xá / Sleepbox / Ở ghép (SLEEPBOX) và nhà nguyên căn ở tỉnh.
7. Tự động nạp và tổng hợp dữ liệu từ SQLite Staging DB + Checkpoint LLM sang file cache Parquet `listings_clean.parquet`.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Tuple
import numpy as np
import pandas as pd

from crawler.config.paths import (
    PROCESSED_DATA_DIR,
    PROCESSED_PARQUET_PATH,
    STAGING_DB_PATH,
    LLM_CHECKPOINT_PATH,
    POI_LOCATIONS_PATH,
)
from crawler.schema.enums import ROOM_TYPE_CODE_TO_ID

DEFAULT_PARQUET_PATH = PROCESSED_PARQUET_PATH
DEFAULT_DATA_PATH = (
    DEFAULT_PARQUET_PATH
    if DEFAULT_PARQUET_PATH.exists()
    else PROCESSED_DATA_DIR / "listings_clean.json"
)

# ==============================================================================
# 1. DANH MỤC TIỆN ÍCH, QUY ĐỊNH & AN NINH CHUẨN HÓA (CANONICAL TAXONOMY 17 FLAGS)
# ==============================================================================

CANONICAL_AMENITY_KEYS = [
    "private_wc",
    "aircon",
    "mezzanine",
    "kitchen",
    "fridge",
    "washing_machine",
    "window_balcony",
    "furniture",
    "parking",
    "elevator",
]

CANONICAL_RULE_KEYS = [
    "free_hours",
    "no_shared_landlord",
    "pet_allowed",
]

CANONICAL_SAFETY_KEYS = [
    "fingerprint_lock",
    "camera",
    "guard",
    "safe_area",
]

ALL_BINARY_KEYS = CANONICAL_AMENITY_KEYS + CANONICAL_RULE_KEYS + CANONICAL_SAFETY_KEYS

# Trọng số tính điểm nội suy amenity_overall (thang 100 điểm) khớp 1-1 với ListingExtraction
AMENITY_WEIGHTS: dict[str, float] = {
    "private_wc": 20.0,
    "aircon": 20.0,
    "mezzanine": 15.0,
    "kitchen": 15.0,
    "fridge": 10.0,
    "washing_machine": 10.0,
    "window_balcony": 10.0,
    "furniture": 5.0,
    "parking": 5.0,
    "elevator": 5.0,
}

# Trọng số tính điểm nội suy safety_score khớp 1-1 với Safety schema
SAFETY_WEIGHTS: dict[str, float] = {
    "camera": 0.30,
    "guard": 0.30,
    "fingerprint_lock": 0.25,
    "safe_area": 0.15,
}

# ==============================================================================
# 2. BIÊN ĐỊA LÝ TOÀN QUỐC & NGƯỠNG THÍCH ỨNG THEO LOẠI PHÒNG
# ==============================================================================

VIETNAM_LAT_RANGE: Tuple[float, float] = (8.0, 23.5)
VIETNAM_LNG_RANGE: Tuple[float, float] = (102.0, 110.0)

# Ngưỡng (area_min, area_max), (price_min, price_max), (ppm_min, ppm_max) theo room_type_id
ROOM_TYPE_FILTER_RULES: dict[int, dict[str, Tuple[float, float]]] = {
    1: {  # ROOM (Phòng trọ truyền thống / phòng ở ghép)
        "area": (6.0, 100.0),
        "price": (500_000.0, 15_000_000.0),
        "ppm": (12_000.0, 500_000.0),
    },
    2: {  # STUDIO (Căn hộ mini / Studio khép kín)
        "area": (12.0, 90.0),
        "price": (1_200_000.0, 20_000_000.0),
        "ppm": (40_000.0, 700_000.0),
    },
    3: {  # APARTMENT (Căn hộ chung cư / share phòng chung cư)
        "area": (15.0, 160.0),
        "price": (1_000_000.0, 30_000_000.0),
        "ppm": (15_000.0, 700_000.0),
    },
    4: {  # SLEEPBOX (Ký túc xá / Sleepbox / Giường tầng ở ghép)
        "area": (3.0, 120.0),
        "price": (400_000.0, 4_500_000.0),
        "ppm": (5_000.0, 800_000.0),
    },
    5: {  # WHOLE_HOUSE (Nhà nguyên căn)
        "area": (12.0, 250.0),
        "price": (1_500_000.0, 35_000_000.0),
        "ppm": (12_000.0, 600_000.0),
    },
}

# ==============================================================================
# 3. DANH MỤC TRUNG TÂM ĐÔ THỊ & ĐẠI HỌC TRỌNG ĐIỂM TOÀN QUỐC (POI)
# ==============================================================================

# Danh mục mặc định dự phòng (Fallback nếu không tìm thấy poi_locations.json)
DEFAULT_FALLBACK_CITY_HUBS: list[tuple[float, float]] = [
    (10.7725, 106.6980),  # TP.HCM - Bến Thành (Quận 1)
    (10.8494, 106.7726),  # TP.HCM - Ngã tư Thủ Đức
    (21.0285, 105.8542),  # Hà Nội - Hồ Hoàn Kiếm
    (21.0333, 105.7833),  # Hà Nội - Cầu Giấy
    (16.0618, 108.2208),  # Đà Nẵng - Hải Châu
    (10.0342, 105.7876),  # Cần Thơ - Bến Ninh Kiều
    (10.9805, 106.6745),  # Bình Dương - Thủ Dầu Một
    (10.9067, 106.7719),  # Bình Dương - Dĩ An
    (10.3460, 107.0843),  # Bà Rịa - Vũng Tàu
    (11.9404, 108.4583),  # Lâm Đồng - Đà Lạt
    (10.9574, 106.8427),  # Đồng Nai - Biên Hòa
    (12.6667, 108.0500),  # Đắk Lắk - Buôn Ma Thuột
    (16.4637, 107.5909),  # Thừa Thiên Huế
    (12.2388, 109.1967),  # Khánh Hòa - Nha Trang
    (20.8600, 106.6800),  # Hải Phòng
    (20.9505, 107.0734),  # Quảng Ninh - Hạ Long
]

DEFAULT_FALLBACK_UNI_HUBS: list[tuple[float, float]] = [
    (10.8752, 106.8007),  # TP.HCM - ĐHQG TP.HCM (Làng đại học Thủ Đức)
    (10.7721, 106.6579),  # TP.HCM - Cụm ĐH Bách Khoa TP.HCM (Quận 10)
    (10.8016, 106.7114),  # TP.HCM - Cụm ĐH HUTECH / UEF / Ngoại Thương CS2 (Bình Thạnh)
    (10.7326, 106.7058),  # TP.HCM - Cụm ĐH RMIT / Tôn Đức Thắng (Quận 7)
    (10.8275, 106.6792),  # TP.HCM - Cụm ĐH Công Nghiệp TP.HCM (Gò Vấp)
    (21.0044, 105.8433),  # Hà Nội - Cụm Bách Khoa - Kinh Tế - Xây Dựng (Hai Bà Trưng)
    (21.0371, 105.7816),  # Hà Nội - Cụm ĐHQG Hà Nội - Sư Phạm (Cầu Giấy)
    (20.9808, 105.7958),  # Hà Nội - Cụm Kiến Trúc - Bưu Chính - An Ninh (Hà Đông)
    (16.0748, 108.1499),  # Đà Nẵng - ĐH Bách Khoa Đà Nẵng (Liên Chiểu)
    (16.0597, 108.2148),  # Đà Nẵng - Cụm ĐH Kinh Tế - ĐH Đà Nẵng
    (10.0312, 105.7690),  # Cần Thơ - ĐH Cần Thơ (Khu II)
    (10.0270, 105.7570),  # Cần Thơ - ĐH Y Dược Cần Thơ
    (21.5833, 105.8167),  # Thái Nguyên - ĐH Thái Nguyên
    (16.4600, 107.5900),  # Huế - ĐH Huế
]


def load_poi_locations_from_config(
    config_path: Path | str = POI_LOCATIONS_PATH,
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Nạp danh mục tọa độ trung tâm đô thị & đại học từ file config JSON (kèm fallback an toàn)."""
    p = Path(config_path)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            cities = [
                (float(item["lat"]), float(item["lng"]))
                for item in data.get("city_hubs", [])
                if "lat" in item and "lng" in item
            ]
            unis = [
                (float(item["lat"]), float(item["lng"]))
                for item in data.get("university_hubs", [])
                if "lat" in item and "lng" in item
            ]
            if cities and unis:
                return cities, unis
        except Exception as e:
            print(f"[POI] Cảnh báo lỗi đọc file {config_path}: {e}. Dùng danh mục mặc định.", flush=True)

    return DEFAULT_FALLBACK_CITY_HUBS, DEFAULT_FALLBACK_UNI_HUBS


# Tự động nạp từ file cấu hình độc lập crawler/config/poi_locations.json
NATIONAL_CITY_HUBS, NATIONAL_UNI_HUBS = load_poi_locations_from_config()


def compute_single_poi_distance(
    lat: float | None,
    lng: float | None,
    poi_coords: list[tuple[float, float]],
) -> float:
    """Tính khoảng cách Haversine tối thiểu (km) từ 1 tọa độ tới danh sách POIs."""
    if lat is None or lng is None or float(lat) == 0.0 or float(lng) == 0.0:
        return 999.0
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (ValueError, TypeError):
        return 999.0

    r_lat = np.radians(lat_f)
    r_lng = np.radians(lng_f)
    pois = np.radians(np.asarray(poi_coords, dtype=float))

    dlat = pois[:, 0] - r_lat
    dlng = pois[:, 1] - r_lng
    a = np.sin(dlat / 2.0) ** 2 + np.cos(r_lat) * np.cos(pois[:, 0]) * np.sin(dlng / 2.0) ** 2
    c = 2.0 * np.arcsin(np.clip(np.sqrt(a), 0.0, 1.0))
    return float(np.min(6371.0 * c))


def compute_haversine_distance_vectorized(
    lats: np.ndarray,
    lngs: np.ndarray,
    poi_coords: list[tuple[float, float]],
) -> np.ndarray:
    """Tính khoảng cách Haversine tối thiểu (km) vector hóa siêu tốc cho mảng tọa độ."""
    if len(lats) == 0:
        return np.array([], dtype=float)

    R = 6371.0
    lat_r = np.radians(np.asarray(lats, dtype=float))[:, None]
    lng_r = np.radians(np.asarray(lngs, dtype=float))[:, None]

    pois = np.radians(np.asarray(poi_coords, dtype=float))
    poi_lat = pois[:, 0][None, :]
    poi_lng = pois[:, 1][None, :]

    dlat = poi_lat - lat_r
    dlng = poi_lng - lng_r
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat_r) * np.cos(poi_lat) * np.sin(dlng / 2.0) ** 2
    c = 2.0 * np.arcsin(np.clip(np.sqrt(a), 0.0, 1.0))
    dists = R * c
    return np.min(dists, axis=1)


# ==============================================================================
# 4. TRÍCH XUẤT ĐẶC TRƯNG TỪ BẢN GHI (FEATURE EXTRACTION)
# ==============================================================================

def _safe_float(val: Any, default: float = 0.0) -> float:
    """Ép kiểu số thực an toàn, xử lý triệt để None, chuỗi lỗi và np.nan."""
    if val is None:
        return default
    try:
        f = float(val)
        return default if np.isnan(f) else f
    except (ValueError, TypeError):
        return default


def extract_features_from_record(r: dict[str, Any]) -> dict[str, Any]:
    """Chuyển 1 record thô thành vector feature dict chuẩn hóa Toàn Quốc cho ML.

    Đảm bảo tính bất biến (Immutability): không thay đổi dict `r` truyền vào.
    """
    lid = str(r.get("listing_id") or r.get("id") or "")
    area_m2 = _safe_float(r.get("area_m2"), default=0.0)
    lat = _safe_float(r.get("lat"), default=0.0)
    lng = _safe_float(r.get("lng"), default=0.0)
    price_vnd = _safe_float(r.get("price_vnd"), default=0.0)
    raw_furnishing = _safe_float(r.get("furnishing_code"), default=2.0)
    furnishing_code = raw_furnishing if raw_furnishing > 0 else 2.0

    # Đọc report và concept_scores (hỗ trợ cả dict lẫn JSON string từ Parquet)
    concept = r.get("concept_scores")
    if isinstance(concept, str) and concept.strip().startswith("{"):
        try:
            concept = json.loads(concept)
        except Exception:
            concept = {}
    if not isinstance(concept, dict):
        concept = {}

    report = r.get("report")
    if isinstance(report, str) and report.strip().startswith("{"):
        try:
            report = json.loads(report)
        except Exception:
            report = {}
    if not isinstance(report, dict):
        report = {}

    rep_amenities = report.get("amenities") if isinstance(report.get("amenities"), dict) else {}
    rep_rules = report.get("rules") if isinstance(report.get("rules"), dict) else {}
    rep_safety = report.get("safety") if isinstance(report.get("safety"), dict) else {}

    # Phân loại phòng (room_type_id: 1..5)
    rt_id = r.get("room_type_id")
    if isinstance(rt_id, (int, float)) and int(rt_id) in (1, 2, 3, 4, 5):
        resolved_rt_id = int(rt_id)
    else:
        rt_code = str(r.get("room_type") or "").strip().upper()
        if not rt_code and isinstance(report.get("room_type"), str):
            rt_code = str(report.get("room_type")).strip().upper()
        resolved_rt_id = ROOM_TYPE_CODE_TO_ID.get(rt_code, 1)

    row: dict[str, Any] = {
        "listing_id": lid,
        "area_m2": area_m2,
        "lat": lat,
        "lng": lng,
        "price_vnd": price_vnd,
        "room_type_id": resolved_rt_id,
        "furnishing_code": furnishing_code,
    }

    # Trích xuất 17 cờ nhị phân chuẩn hóa
    for k in ALL_BINARY_KEYS:
        val = 0
        if k in concept:
            try:
                val = 1 if float(concept[k]) >= 0.8 else 0
            except (ValueError, TypeError):
                val = 0
        elif k in rep_amenities:
            sig = rep_amenities[k]
            v = sig.get("value") if isinstance(sig, dict) else getattr(sig, "value", None)
            val = 1 if v == "yes" else 0
        elif k in rep_rules:
            sig = rep_rules[k]
            v = sig.get("value") if isinstance(sig, dict) else getattr(sig, "value", None)
            val = 1 if v == "yes" else 0
        elif k in rep_safety:
            sig = rep_safety[k]
            v = sig.get("value") if isinstance(sig, dict) else getattr(sig, "value", None)
            val = 1 if v == "yes" else 0

        row[f"is_{k}"] = int(val)

    # Điểm chất lượng ngữ nghĩa LLM (amenity_overall và safety_score)
    # 1. amenity_overall: ưu tiên lấy điểm có sẵn trong bản ghi, fallback nội suy từ 10 cờ tiện ích
    if r.get("amenity_overall") is not None:
        try:
            row["amenity_overall"] = float(r["amenity_overall"])
        except (ValueError, TypeError):
            row["amenity_overall"] = 0.0
    elif report.get("amenity_overall") is not None or report.get("amenity_overall_score") is not None:
        raw_sc = report.get("amenity_overall") if report.get("amenity_overall") is not None else report.get("amenity_overall_score")
        try:
            row["amenity_overall"] = float(raw_sc)
        except (ValueError, TypeError):
            row["amenity_overall"] = 0.0
    else:
        earned_amen = sum(AMENITY_WEIGHTS[k] for k in AMENITY_WEIGHTS if row.get(f"is_{k}") == 1)
        row["amenity_overall"] = round(min(1.0, earned_amen / 100.0), 2)

    # 2. safety_score: ưu tiên lấy điểm có sẵn trong bản ghi, fallback nội suy từ 4 cờ an ninh
    if r.get("safety_score") is not None:
        try:
            row["safety_score"] = float(r["safety_score"])
        except (ValueError, TypeError):
            row["safety_score"] = 0.0
    elif report.get("safety_score") is not None:
        try:
            row["safety_score"] = float(report["safety_score"])
        except (ValueError, TypeError):
            row["safety_score"] = 0.0
    else:
        earned_safe = sum(SAFETY_WEIGHTS[k] for k in SAFETY_WEIGHTS if row.get(f"is_{k}") == 1)
        row["safety_score"] = round(min(1.0, earned_safe), 2)

    # 3. Khoảng cách Haversine POI Toàn Quốc
    dist_hub = compute_single_poi_distance(lat, lng, NATIONAL_CITY_HUBS)
    dist_uni = compute_single_poi_distance(lat, lng, NATIONAL_UNI_HUBS)
    row["dist_nearest_hub_km"] = round(dist_hub, 2)
    row["dist_nearest_uni_km"] = round(dist_uni, 2)

    return row


# ==============================================================================
# 5. BỘ LỌC DỮ LIỆU SẠCH (DATA CLEANING & ADAPTIVE FILTERING)
# ==============================================================================

def filter_valid_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Lọc bỏ các bản ghi không hợp lệ theo Bounding Box Toàn Quốc và ngưỡng thích ứng từng loại phòng."""
    if df.empty:
        return df.copy()

    # 1. Bounding box Toàn Việt Nam
    cond_geo = (
        (df["lat"] >= VIETNAM_LAT_RANGE[0])
        & (df["lat"] <= VIETNAM_LAT_RANGE[1])
        & (df["lng"] >= VIETNAM_LNG_RANGE[0])
        & (df["lng"] <= VIETNAM_LNG_RANGE[1])
    )
    df_valid = df[cond_geo].copy()
    if df_valid.empty:
        return df_valid

    # 2. Ngưỡng theo room_type_id
    ppm = df_valid["price_vnd"] / df_valid["area_m2"].clip(lower=1e-6)
    keep_mask = pd.Series(False, index=df_valid.index)

    for rt_id, rules in ROOM_TYPE_FILTER_RULES.items():
        rt_mask = df_valid["room_type_id"] == rt_id
        area_min, area_max = rules["area"]
        price_min, price_max = rules["price"]
        ppm_min, ppm_max = rules["ppm"]

        valid_for_rt = (
            rt_mask
            & (df_valid["area_m2"] >= area_min)
            & (df_valid["area_m2"] <= area_max)
            & (df_valid["price_vnd"] >= price_min)
            & (df_valid["price_vnd"] <= price_max)
            & (ppm >= ppm_min)
            & (ppm <= ppm_max)
        )
        keep_mask = keep_mask | valid_for_rt

    # Xử lý các phòng có room_type_id ngoài 1..5 (fallback sang rule ROOM 1)
    other_mask = ~df_valid["room_type_id"].isin(ROOM_TYPE_FILTER_RULES.keys())
    if other_mask.any():
        default_rule = ROOM_TYPE_FILTER_RULES[1]
        area_min, area_max = default_rule["area"]
        price_min, price_max = default_rule["price"]
        ppm_min, ppm_max = default_rule["ppm"]
        valid_other = (
            other_mask
            & (df_valid["area_m2"] >= area_min)
            & (df_valid["area_m2"] <= area_max)
            & (df_valid["price_vnd"] >= price_min)
            & (df_valid["price_vnd"] <= price_max)
            & (ppm >= ppm_min)
            & (ppm <= ppm_max)
        )
        keep_mask = keep_mask | valid_other

    return df_valid[keep_mask].reset_index(drop=True)


def export_records_to_parquet(records: list[dict[str, Any]], output_path: str | Path) -> Path:
    """Xuất danh sách records sạch ra file Parquet nhị phân chuẩn hóa JSON string cho dict struct."""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        pd.DataFrame().to_parquet(out_path, index=False)
        return out_path

    normalized_rows = []
    for r in records:
        row = dict(r)
        for k, v in list(row.items()):
            if isinstance(v, dict):
                row[k] = json.dumps(v, ensure_ascii=False)
        normalized_rows.append(row)

    df = pd.DataFrame(normalized_rows)
    df.to_parquet(out_path, index=False)
    return out_path


def _build_or_load_clean_dataset() -> list[dict[str, Any]]:
    """Tự động tổng hợp 10.430+ bản ghi từ SQLite Staging DB và Checkpoint LLM, lưu ra Parquet."""
    from crawler.etl.extract import extract_raw_listings
    from crawler.etl.transform import ListingTransformer

    if not STAGING_DB_PATH.exists():
        print(f"[DATA] Không tìm thấy Staging DB tại: {STAGING_DB_PATH}", flush=True)
        return []

    print(f"[DATA] Đang trích xuất dữ liệu từ Staging DB: {STAGING_DB_PATH}...", flush=True)
    raw_listings = extract_raw_listings(limit=None)
    if not raw_listings:
        print("[DATA] Staging DB rỗng, không có bản ghi nào.", flush=True)
        return []

    ckpt_path = LLM_CHECKPOINT_PATH if LLM_CHECKPOINT_PATH.exists() else None
    print(f"[DATA] Đang làm sạch và tích hợp báo cáo LLM từ {ckpt_path} cho {len(raw_listings)} bản ghi...", flush=True)
    transformer = ListingTransformer(llm_reports=ckpt_path)
    clean_records = transformer.transform(raw_listings, active_only=False)

    try:
        export_records_to_parquet(clean_records, PROCESSED_PARQUET_PATH)
        print(f"[DATA] Đã lưu cache thành công {len(clean_records)} bản ghi sạch vào: {PROCESSED_PARQUET_PATH}", flush=True)
    except Exception as e:
        print(f"[DATA] Cảnh báo không thể lưu cache Parquet: {e}", flush=True)

    return clean_records


# ==============================================================================
# 6. HÀM CHÍNH NẠP DATASET CHO HUẤN LUYỆN ML
# ==============================================================================

def load_and_preprocess_dataset(
    data_path: str | Path = DEFAULT_DATA_PATH,
    auto_build_cache: bool = True,
    **kwargs: Any,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Nạp dataset từ Parquet (ưu tiên) hoặc JSON/Staging DB, áp dụng bộ lọc Toàn Quốc và trả về (X, y)."""
    path_obj = Path(data_path)

    # 1. Tìm hoặc tự động tổng hợp dữ liệu
    if not path_obj.exists():
        if DEFAULT_PARQUET_PATH.exists():
            path_obj = DEFAULT_PARQUET_PATH
        elif auto_build_cache:
            print("[DATA] Chưa có file dữ liệu sạch, bắt đầu tự động tổng hợp từ Staging DB & Checkpoint LLM...")
            raw_data = _build_or_load_clean_dataset()
            if not raw_data:
                raise FileNotFoundError(f"Không thể nạp dữ liệu từ {data_path} hoặc Staging DB.")
            path_obj = None
        else:
            raise FileNotFoundError(f"Không tìm thấy file dữ liệu tại: {path_obj}")

    if path_obj is not None:
        if path_obj.suffix.lower() == ".parquet":
            raw_df = pd.read_parquet(path_obj)
            raw_data = raw_df.to_dict(orient="records")
        else:
            with open(path_obj, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

    # 2. Trích xuất đặc trưng cho từng bản ghi
    extracted_rows = [extract_features_from_record(r) for r in raw_data]
    df = pd.DataFrame(extracted_rows)

    # 3. Lọc dữ liệu thích ứng theo Bounding Box Toàn Quốc và loại phòng
    df_clean = filter_valid_dataframe(df)

    y = df_clean["price_vnd"].copy()
    X = df_clean.drop(columns=["listing_id", "price_vnd"]).copy()

    return X, y


if __name__ == "__main__":
    X, y = load_and_preprocess_dataset()
    print("=" * 60)
    print("   BÁO CÁO TRÍCH XUẤT ĐẶC TRƯNG TOÀN QUỐC (FEATURE EXTRACTOR v2)")
    print("=" * 60)
    print(f"Số lượng bản ghi sạch: {len(X):,} dòng")
    print(f"Số lượng features: {len(X.columns)} đặc trưng")
    print(f"Danh sách features: {X.columns.tolist()}")
    print("\nPhân bố theo room_type_id:")
    print(X["room_type_id"].value_counts().sort_index())
    print("\nThống kê biến mục tiêu y (price_vnd):")
    print(y.describe().apply(lambda v: f"{v:,.0f}"))
