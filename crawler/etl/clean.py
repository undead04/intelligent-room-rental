import os
import sys

# Tự động thêm thư mục gốc dự án vào sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from crawler.etl.pipeline import run_pipeline

def combine_and_clean():
    """
    Hàm wrapper tương thích ngược.
    Gọi trực tiếp pipeline ETL (Extract -> Transform -> Load ra CSV).
    """
    return run_pipeline(destinations=["csv"])

if __name__ == "__main__":
    combine_and_clean()
