import os
import json
import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw', 'listings')
PROCESSED_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'processed', 'listings_clean.csv')

def combine_and_clean():
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    
    all_data = []
    
    if not os.path.exists(RAW_DIR):
        print("Chưa có dữ liệu thô.")
        return
        
    for fname in os.listdir(RAW_DIR):
        if fname.endswith(".json"):
            file_path = os.path.join(RAW_DIR, fname)
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    all_data.append(data)
                except Exception as e:
                    print(f"Lỗi đọc file {fname}: {e}")
                    
    if not all_data:
        print("Không có bản ghi nào để xử lý.")
        return
        
    df = pd.DataFrame(all_data)
    
    # 1. Khử trùng lặp
    df = df.drop_duplicates(subset=['listing_id'])
    
    # 2. Xử lý missing values cơ bản
    df['price_vnd'] = df['price_vnd'].fillna(0)
    df['area_m2'] = df['area_m2'].fillna(0)
    
    # (Đã bỏ phần trích xuất tiện ích theo yêu cầu của user, chỉ dùng nội dung description)

    # Lưu ra CSV
    df.to_csv(PROCESSED_FILE, index=False, encoding="utf-8-sig")
    print(f"Đã lưu {len(df)} bản ghi đã làm sạch vào {PROCESSED_FILE}")
    
    # In ra một số thống kê nhanh
    print("\nThống kê số lượng theo Quận/Huyện:")
    if 'district' in df.columns:
        print(df['district'].value_counts())

if __name__ == "__main__":
    combine_and_clean()
