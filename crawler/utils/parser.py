from datetime import datetime

def parse_chotot_item(item):
    """Map dữ liệu từ Chợ Tốt JSON sang raw schema, bổ sung thông tin người đăng và ML/UI"""
    ad_id = str(item.get('list_id') or item.get('ad_id'))
    
    # Xử lý timestamp
    posted_date = None
    list_time = item.get('list_time')
    if list_time:
        try:
            posted_date = datetime.fromtimestamp(list_time / 1000.0).isoformat()
        except:
            pass
            
    # Lấy thông tin phụ cho UI và Train
    seller_info = item.get('seller_info', {})
    furnishing = ""
    # Trích xuất nội thất từ feature_params nếu có
    feature_params = item.get('feature_params', {}).get('seo_structure', {}).get('items', [])
    for feat in feature_params:
        if feat.get('id') == 'furnishing_rent':
            furnishing = feat.get('value', '')

    return {
        # --- THÔNG TIN ĐỊNH DANH BÀI ĐĂNG ---
        "listing_id": f"nhatot_{ad_id}",
        "source": "nhatot",
        "url": f"https://www.nhatot.com/phong-tro/{ad_id}.htm",
        
        # --- THÔNG TIN DÀNH CHO GIAO DIỆN HIỂN THỊ (UI/WEBSITE) ---
        "title": item.get('subject', ''),
        "price_string": item.get('price_string', ''), # Hiển thị "3,5 triệu/tháng"
        "images": item.get('images', []),
        "description": item.get('body', ''),
        "address_raw": item.get('address', '') or f"{item.get('street_name', '')}, {item.get('ward_name', '')}, {item.get('area_name', '')}",
        
        # --- THÔNG TIN NGƯỜI ĐĂNG (DÀNH CHO UI VÀ PHÂN TÍCH ĐỘ TIN CẬY) ---
        "poster_id": item.get('account_id'),
        "poster_name": item.get('account_name', ''),
        "poster_avatar": item.get('avatar', ''),
        "poster_live_ads": seller_info.get('live_ads', 0), # Số lượng bài đang đăng
        "poster_sold_ads": seller_info.get('sold_ads', 0), # Số lượng bài đã bán/cho thuê
        "is_company_ad": item.get('company_ad', False), # Đăng bởi môi giới/công ty hay cá nhân
        
        # --- THÔNG TIN ĐỂ HUẤN LUYỆN MÔ HÌNH (ML TRAINING) ---
        "price_vnd": item.get('price', 0),
        "area_m2": item.get('size', 0),
        "price_million_per_m2": item.get('price_million_per_m2', 0), # Feature quan trọng để dự đoán giá
        "deposit": item.get('deposit', 0), # Tiền cọc (nếu có)
        "furnishing": furnishing, # Tình trạng nội thất
        "room_type": "phòng trọ",
        "ward": item.get('ward_name', ''),
        "district": item.get('area_name', ''),
        "city": item.get('region_name', ''),
        "street_name": item.get('street_name', ''),
        "lat": item.get('latitude'),
        "lng": item.get('longitude'),
        
        # --- METADATA ---
        "posted_date": posted_date,
        "crawled_at": datetime.now().isoformat()
    }
