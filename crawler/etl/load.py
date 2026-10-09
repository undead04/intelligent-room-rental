import os
import sys
import csv
from collections import Counter

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_PROCESSED_CSV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "processed", "listings_clean.csv"))

class DataLoader:
    """
    [LOAD STAGE]
    Chịu trách nhiệm lưu trữ và nạp dữ liệu sạch vào các đích đến (Destinations):
    1. CSV (`listings_clean.csv`) - Dùng cho phân tích nhanh, báo cáo
    2. Parquet - Dùng cho huấn luyện mô hình Machine Learning
    3. PostgreSQL / Database - Nạp vào CSDL hệ thống
    
    >>> Bạn có thể dán (paste) thêm code kết nối DB từ Colab vào class này.
    """

    def __init__(self):
        pass

    def load_to_csv(self, records: list[dict], output_path: str = None) -> str:
        """Xuất danh sách records ra file CSV (chuẩn UTF-8 BOM để Excel đọc không lỗi font)"""
        target_path = output_path or DEFAULT_PROCESSED_CSV
        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        if not records:
            print("[LOAD] Không có bản ghi nào để lưu ra CSV.", flush=True)
            return target_path

        # Thu thập đầy đủ các cột dữ liệu
        fieldnames = list(records[0].keys())
        for r in records[1:]:
            for k in r.keys():
                if k not in fieldnames:
                    fieldnames.append(k)

        with open(target_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)

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

    def load_to_postgres(self, records: list[dict], db_url: str = None, table_name: str = "listings"):
        """
        [HOOK / PLACEHOLDER]: Nạp dữ liệu vào PostgreSQL
        Dùng cho code nạp DB từ Colab / Backend.
        """
        print(f"[LOAD] Khung nạp PostgreSQL sẵn sàng (Bảng: {table_name}). Dán code SQLAlchemy/psycopg2 từ Colab vào đây.", flush=True)
        # TODO: User sẽ bổ sung logic insert DB từ Colab vào đây khi sẵn sàng.
        pass

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
    loader = DataLoader()
    sample_data = [{"listing_id": "test_1", "title": "Phòng trọ test", "price_vnd": 3000000, "is_active": True}]
    loader.load_to_csv(sample_data, "test_out.csv")
    loader.print_summary(sample_data)
    if os.path.exists("test_out.csv"):
        os.remove("test_out.csv")
