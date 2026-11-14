from datetime import datetime
import re
from typing import Optional


def _extract_positive_int(val: object) -> Optional[int]:
    """Trích xuất số nguyên dương (> 0) từ int/float/str; bỏ qua bool và giá trị <= 0."""
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        num = int(val)
        return num if num > 0 else None
    if isinstance(val, str):
        match = re.search(r"\d+", val)
        if match:
            num = int(match.group(0))
            return num if num > 0 else None
    return None


def parse_chotot_item(item):
    """Map dữ liệu từ Chợ Tốt JSON sang raw schema chuẩn hóa đầy đủ dựa theo test_output"""
    list_id = str(item.get('list_id') or item.get('ad_id', ''))
    ad_id = str(item.get('ad_id') or item.get('list_id', ''))
    
    # Xử lý timestamp (list_time ở dạng milliseconds epoch)
    posted_date = None
    list_time = item.get('list_time') or item.get('orig_list_time')
    if list_time:
        try:
            posted_date = datetime.fromtimestamp(list_time / 1000.0).isoformat()
        except Exception:
            pass

    # Lấy thông tin người đăng & seller_info
    seller_info = item.get('seller_info', {}) or {}
    poster_name = (
        item.get('account_name') 
        or item.get('full_name') 
        or seller_info.get('full_name') 
        or ''
    ).strip()
    poster_avatar = item.get('avatar') or seller_info.get('avatar') or ''

    # Lấy tình trạng nội thất, số phòng ngủ & phòng vệ sinh từ feature_params (seo_structure hoặc compare)
    furnishing = ""
    bedrooms_feat = None
    bathrooms_feat = None
    feature_params = item.get('feature_params', {}) or {}
    seo_items = feature_params.get('seo_structure', {}).get('items', [])
    compare_items = feature_params.get('compare', {}).get('items', [])
    
    for feat in seo_items + compare_items:
        fid = feat.get('id')
        if fid == 'furnishing_rent' and not furnishing:
            furnishing = feat.get('value', '')
        elif fid in ('rooms', 'bedrooms') and bedrooms_feat is None:
            bedrooms_feat = _extract_positive_int(feat.get('value'))
        elif fid in ('toilets', 'bathrooms') and bathrooms_feat is None:
            bathrooms_feat = _extract_positive_int(feat.get('value'))

    bedrooms = _extract_positive_int(item.get('rooms'))
    if bedrooms is None:
        bedrooms = _extract_positive_int(item.get('bedrooms'))
    if bedrooms is None:
        bedrooms = bedrooms_feat

    bathrooms = _extract_positive_int(item.get('toilets'))
    if bathrooms is None:
        bathrooms = _extract_positive_int(item.get('bathrooms'))
    if bathrooms is None:
        bathrooms = bathrooms_feat

    # Trích xuất địa chỉ đầy đủ (address_raw)
    street_name = item.get('street_name', '') or ''
    ward_name = item.get('ward_name', '') or item.get('ward_name_v3', '') or ''
    area_name = item.get('area_name', '') or ''
    region_name = item.get('region_name', '') or item.get('region_name_v3', '') or ''

    address_parts = [p for p in [street_name, ward_name, area_name, region_name] if p]
    address_raw = item.get('address') or ", ".join(address_parts)

    now_iso = datetime.now().isoformat()

    return {
        # --- THÔNG TIN ĐỊNH DANH BÀI ĐĂNG ---
        "listing_id": f"nhatot_{list_id}",
        "ad_id": ad_id,
        "list_id": list_id,
        "source": "nhatot",
        "url": f"https://www.nhatot.com/phong-tro/{list_id}.htm",
        
        # --- TRẠNG THÁI HOẠT ĐỘNG (ACTIVE/EXPIRED) ---
        "is_active": True,
        "status": item.get('status', 'active'),
        "last_checked_at": now_iso,
        
        # --- THÔNG TIN GIAO DIỆN HIỂN THỊ (UI/WEBSITE) ---
        "title": item.get('subject', ''),
        "price_string": item.get('price_string', ''), # Ví dụ: "3,5 triệu/tháng"
        "images": item.get('images', []),
        "main_image": item.get('image') or item.get('thumbnail_image') or '',
        "description": item.get('body', ''),
        "address_raw": address_raw,
        
        # --- THÔNG TIN NGƯỜI ĐĂNG & LIÊN HỆ ---
        "poster_id": item.get('account_id'),
        "poster_name": poster_name,
        "poster_avatar": poster_avatar,
        "phone": item.get('phone', ''), # Số điện thoại (nếu có, thường ở dạng masked 081701**** trên Chợ Tốt)
        "poster_live_ads": seller_info.get('live_ads', 0),
        "poster_sold_ads": seller_info.get('sold_ads', 0),
        "is_company_ad": bool(item.get('company_ad', False)),
        
        # --- THÔNG TIN TRAIN MODEL (ML FEATURES) ---
        "price_vnd": item.get('price', 0),
        "area_m2": item.get('size', 0),
        "price_million_per_m2": item.get('price_million_per_m2', 0),
        "deposit": item.get('deposit', 0),
        "furnishing": furnishing,
        "furnishing_code": item.get('furnishing_rent'), # Code 1, 2, 3...
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "room_type": item.get('category_name') or "Phòng trọ",
        "category_id": item.get('category'),
        "ward": ward_name,
        "district": area_name,
        "city": region_name,
        "street_name": street_name,
        "ward_id": item.get('ward'),
        "district_id": item.get('area'),
        "region_id": item.get('region'),
        "lat": item.get('latitude'),
        "lng": item.get('longitude'),
        
        # --- METADATA ---
        "posted_date": posted_date,
        "crawled_at": now_iso
    }
