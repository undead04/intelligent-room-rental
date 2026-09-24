from datetime import datetime

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

    # Lấy tình trạng nội thất từ feature_params (seo_structure hoặc compare)
    furnishing = ""
    feature_params = item.get('feature_params', {}) or {}
    seo_items = feature_params.get('seo_structure', {}).get('items', [])
    compare_items = feature_params.get('compare', {}).get('items', [])
    
    for feat in seo_items + compare_items:
        if feat.get('id') == 'furnishing_rent':
            furnishing = feat.get('value', '')
            break

    # Trích xuất địa chỉ đầy đủ (address_raw)
    street_name = item.get('street_name', '') or ''
    ward_name = item.get('ward_name', '') or item.get('ward_name_v3', '') or ''
    area_name = item.get('area_name', '') or ''
    region_name = item.get('region_name', '') or item.get('region_name_v3', '') or ''

    address_parts = [p for p in [street_name, ward_name, area_name, region_name] if p]
    address_raw = item.get('address') or ", ".join(address_parts)

    return {
        # --- THÔNG TIN ĐỊNH DANH BÀI ĐĂNG ---
        "listing_id": f"nhatot_{list_id}",
        "ad_id": ad_id,
        "list_id": list_id,
        "source": "nhatot",
        "url": f"https://www.nhatot.com/phong-tro/{list_id}.htm",
        
        # --- THÔNG TIN GIAO DIỆN HIỂN THỊ (UI/WEBSITE) ---
        "title": item.get('subject', ''),
        "price_string": item.get('price_string', ''), # Ví dụ: "3,5 triệu/tháng"
        "images": item.get('images', []),
        "main_image": item.get('image') or item.get('thumbnail_image') or '',
        "description": item.get('body', ''),
        "address_raw": address_raw,
        
        # --- THÔNG TIN NGƯỜI ĐĂNG ---
        "poster_id": item.get('account_id'),
        "poster_name": poster_name,
        "poster_avatar": poster_avatar,
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
        "crawled_at": datetime.now().isoformat()
    }
