"""Script quét và làm giàu điểm tiện nghi (concept_scores, amenity_overall, safety_score)
cho toàn bộ tin đăng trong cơ sở dữ liệu PostgreSQL dựa trên tiêu đề và mô tả thực tế.
"""

import json
import logging
import re
import sys
import unicodedata
import psycopg2
from psycopg2.extras import execute_batch

logging.basicConfig(level=logging.INFO, format="[ENRICH] %(message)s")
logger = logging.getLogger(__name__)

DB_PARAMS = {
    "dbname": "smart_housing_db",
    "user": "postgres",
    "password": "ny300998",
    "host": "localhost",
    "port": 5432,
}


def extract_amenity_signals(title: str, description: str) -> dict:
    raw_text = f"{title or ''} {description or ''}"
    text = unicodedata.normalize("NFC", raw_text).lower()

    # 1. Mezzanine (Gác lửng / có gác / gác cao / gác lưng)
    no_gac = bool(re.search(r"(?:không|ko|chưa)\s*(?:có\s*)?gác", text))
    has_gac = bool(re.search(r"\bgác\b|gác\s*(?:lửng|cao|lưng|lững|đúc|xép|gỗ|lầu)|có\s*gác", text))
    mezzanine = 0.0 if no_gac else (1.0 if has_gac else 0.0)

    # 2. Aircon (Máy lạnh / điều hòa)
    no_ac = bool(re.search(r"(?:không|ko|chưa)\s*(?:có\s*)?(?:máy\s*lạnh|điều\s*hòa)", text))
    has_ac = bool(re.search(r"máy\s*lạnh|điều\s*hòa|\bac\b|may\s*lanh|dieu\s*hoa", text))
    aircon = 0.0 if no_ac else (1.0 if has_ac else 0.0)

    # 3. Private WC
    is_wc_chung = bool(re.search(r"wc\s*chung|vệ\s*sinh\s*chung", text))
    has_wc_rieng = bool(re.search(r"wc\s*riêng|vệ\s*sinh\s*riêng|khép\s*kín|toilet\s*riêng|tolet\s*riêng|phòng\s*tắm\s*riêng", text))
    private_wc = 0.0 if is_wc_chung else (1.0 if has_wc_rieng else 0.5)

    # 4. Kitchen (Bếp / nấu ăn)
    no_cook = bool(re.search(r"(?:không|cấm)\s*nấu\s*ăn", text))
    has_kitchen = bool(re.search(r"kệ\s*bếp|bếp|nấu\s*ăn|khu\s*bếp|cho\s*nấu\s*ăn", text))
    kitchen = 0.0 if no_cook else (1.0 if has_kitchen else 0.0)

    # 5. Fridge (Tủ lạnh)
    fridge = 1.0 if bool(re.search(r"tủ\s*lạnh|tu\s*lanh", text)) else 0.0

    # 6. Washing machine (Máy giặt)
    washing_machine = 1.0 if bool(re.search(r"máy\s*giặt|may\s*giat", text)) else 0.0

    # 7. Window / Balcony (Ban công / cửa sổ)
    window_balcony = 1.0 if bool(re.search(r"ban\s*công|cửa\s*sổ|ban\s*cong|cua\s*so|view\s*thoáng", text)) else 0.0

    # 8. Furniture (Nội thất)
    furniture = 1.0 if bool(re.search(r"nội\s*thất|full\s*đồ|giường|tủ\s*đồ|kệ\s*dép|bàn\s*ghế|nệm", text)) else 0.0

    # 9. Parking (Chỗ để xe)
    parking = 1.0 if bool(re.search(r"để\s*xe|giữ\s*xe|nhà\s*xe|bãi\s*xe|hầm\s*xe", text)) else 0.5

    # 10. Elevator (Thang máy)
    elevator = 1.0 if bool(re.search(r"thang\s*máy|thang\s*may", text)) else 0.0

    # 11. Fingerprint lock / Smart lock
    fingerprint_lock = 1.0 if bool(re.search(r"vân\s*tay|thẻ\s*từ|khoá\s*từ|khóa\s*từ", text)) else 0.0

    # 12. Camera
    camera = 1.0 if bool(re.search(r"camera", text)) else 0.0

    # 13. Guard (Bảo vệ)
    guard = 1.0 if bool(re.search(r"bảo\s*vệ|an\s*ninh\s*24", text)) else 0.0

    # 14. Safe area
    safe_area = 1.0 if bool(re.search(r"an\s*ninh|yên\s*tĩnh", text)) else 0.5

    # 15. Free hours (Giờ giấc tự do)
    free_hours = 1.0 if bool(re.search(r"giờ\s*(?:giấc\s*)?tự\s*do|không\s*chung\s*chủ|ko\s*chung\s*chủ|24/24|24/7|ra\s*vào\s*tự\s*do", text)) else 0.5

    # 16. No shared landlord (Không chung chủ)
    no_shared_landlord = 1.0 if bool(re.search(r"không\s*chung\s*chủ|ko\s*chung\s*chủ|lối\s*đi\s*riêng", text)) else 0.5

    # 17. Pet allowed
    cấm_pet = bool(re.search(r"(?:cấm|không\s*cho)\s*(?:nuôi\s*)?(?:thú\s*cưng|pet|chó|mèo)", text))
    cho_pet = bool(re.search(r"(?:cho\s*)?nuôi\s*(?:thú\s*cưng|pet|chó|mèo)", text))
    pet_allowed = 0.0 if cấm_pet else (1.0 if cho_pet else 0.0)

    # Tính amenity_overall chuẩn hóa
    amenity_pts = 0
    if private_wc == 1.0:
        amenity_pts += 20
    elif private_wc == 0.5:
        amenity_pts += 10
    if aircon == 1.0:
        amenity_pts += 20
    if mezzanine == 1.0:
        amenity_pts += 15
    if kitchen == 1.0:
        amenity_pts += 10
    if fridge == 1.0:
        amenity_pts += 10
    if washing_machine == 1.0:
        amenity_pts += 10
    if window_balcony == 1.0:
        amenity_pts += 10
    if furniture == 1.0:
        amenity_pts += 5

    amenity_overall = round(amenity_pts / 100.0, 2)
    safety_score = round(0.30 * camera + 0.30 * guard + 0.25 * fingerprint_lock + 0.15 * safe_area, 2)

    concept_scores = {
        "private_wc": private_wc,
        "aircon": aircon,
        "mezzanine": mezzanine,
        "kitchen": kitchen,
        "fridge": fridge,
        "washing_machine": washing_machine,
        "window_balcony": window_balcony,
        "furniture": furniture,
        "parking": parking,
        "elevator": elevator,
        "free_hours": free_hours,
        "no_shared_landlord": no_shared_landlord,
        "pet_allowed": pet_allowed,
        "camera": camera,
        "guard": guard,
        "fingerprint_lock": fingerprint_lock,
        "safe_area": safe_area,
    }

    return {
        "concept_scores": concept_scores,
        "amenity_overall": amenity_overall,
        "safety_score": safety_score,
    }


def main():
    conn = psycopg2.connect(**DB_PARAMS)
    cur = conn.cursor()

    cur.execute("SELECT id, title, description, concept_scores, amenity_overall, safety_score FROM listings;")
    rows = cur.fetchall()
    logger.info(f"Đang phân tích và làm giàu tiện nghi cho {len(rows)} tin đăng trong cơ sở dữ liệu...")

    update_payload = []
    gac_count = 0
    ac_count = 0

    for r in rows:
        lid, title, desc, existing_concept, existing_amenity, existing_safety = r
        signals = extract_amenity_signals(title, desc)

        if signals["concept_scores"]["mezzanine"] == 1.0:
            gac_count += 1
        if signals["concept_scores"]["aircon"] == 1.0:
            ac_count += 1

        update_payload.append((
            json.dumps(signals["concept_scores"]),
            signals["amenity_overall"],
            signals["safety_score"],
            lid,
        ))

    update_sql = """
        UPDATE listings
        SET concept_scores = %s::json,
            amenity_overall = %s,
            safety_score = %s
        WHERE id = %s;
    """
    execute_batch(cur, update_sql, update_payload, page_size=200)
    conn.commit()
    cur.close()
    conn.close()

    logger.info(f"ĐÃ CẬP NHẬT THÀNH CÔNG {len(update_payload)} TIN ĐĂNG!")
    logger.info(f"- Số tin đăng có gác (mezzanine = 1.0): {gac_count}")
    logger.info(f"- Số tin đăng có máy lạnh (aircon = 1.0): {ac_count}")


if __name__ == "__main__":
    main()
