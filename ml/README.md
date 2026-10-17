# 🧠 ML Module — Conformal Prediction & Room Price Evaluator (`ml/`)

Module **Machine Learning (`ml/`)** chịu trách nhiệm huấn luyện và suy luận mô hình thẩm định mức độ hợp lý của giá thuê phòng trọ (**`price_score`**). Thay vì sử dụng phép chia thô `price_per_m2` (vốn sai lệch nặng khi phòng diện tích nhỏ hoặc phòng Studio full nội thất), hệ thống dự đoán khoảng giá hợp lý $[P_{\text{low}}, P_{\text{high}}]$ theo từng phân khúc và quy đổi thành điểm số chuẩn hóa `price_score` $\in [0.0, 1.0]$.

---

## 📂 1. Cấu Trúc Thư Mục

```text
ml/
├── __init__.py                  # Export PriceEvaluator / RoomPriceEvaluator
├── feature_extractor.py         # Trích xuất đặc trưng (Vị trí, Diện tích, Tiện ích, An ninh)
├── models.py                    # Kiến trúc CatBoost + Ridge Blend & Mondrian Conformal Prediction
├── price_evaluator.py           # Service suy luận (Inference) tính price_score theo lô/đơn lẻ
├── train_price_model.py         # Script huấn luyện model & xuất artifacts (.joblib)
├── artifacts/                   # Thư mục lưu model đã huấn luyện
│   ├── rent_pipeline.joblib     # Trọng số ensemble & Mondrian interval
│   └── guard.joblib             # Bộ lọc ngoại lai InputGuard
└── notebooks/                   # Jupyter Notebooks thực nghiệm & EDA
```

---

## ⚙️ 2. Cơ Sở Toán Học & Thuật Toán

### 2.1. Tập Đặc Trưng Đầu Vào (`feature_extractor.py`)
Mỗi tin đăng được trích xuất thành vector đặc trưng kết hợp giữa dữ liệu có cấu trúc và tín hiệu ngữ nghĩa từ LLM:
- **Không gian & Địa lý**: `district`, `ward`, tọa độ `lat`, `lng`, mã hóa mục tiêu không gian (`SpatialTE`).
- **Quy mô & Phân loại**: `area_m2`, `room_type` (`ROOM`, `STUDIO`, `APARTMENT`, `SLEEPBOX`, `WHOLE_HOUSE`), `furnishing_code`.
- **Tiện ích & An ninh**: 10 cờ tiện ích chuẩn hóa (`private_wc`, `aircon`, `mezzanine`, `kitchen`, `fridge`, `washing_machine`, `window_balcony`, `furniture`, `parking`, `elevator`), `amenity_overall` và `safety_score`.

### 2.2. Ensemble & Mondrian Conformal Prediction (`models.py`)
1. **Dự đoán giá kỳ vọng ($P_{\text{mid}}$)**: Kết hợp tuyến tính (Blend) giữa **CatBoost Regressor** và **Ridge Regression** trên không gian logarit $\log(1 + P)$ kèm hiệu chỉnh chệch (Smearing Correction).
2. **Dự đoán khoảng tin cậy ($[P_{\text{low}}, P_{\text{high}}]$)**: Áp dụng **Mondrian Conformal Prediction** (`MondrianPriceInterval`) phân tầng theo khu vực và phân khúc để ước lượng biên dưới $P_{\text{low}}$ và biên trên $P_{\text{high}}$.

### 2.3. Công Thức Tính Điểm Hợp Lý Giá (`price_score`)
Trong không gian logarit $\ell(x) = \ln(1 + x)$:
$$\mu = \frac{\ell(P_{\text{low}}) + \ell(P_{\text{high}})}{2}, \quad \sigma = \max\left(\frac{\ell(P_{\text{high}}) - \ell(P_{\text{low}})}{2}, 10^{-6}\right)$$
$$z = \frac{\ell(P_{\text{actual}}) - \mu}{\sigma}$$
$$\text{price\_score}_{100} = \text{clip}(50 - 25 \cdot z,\ 0,\ 100), \quad \text{price\_score} = \frac{\text{price\_score}_{100}}{100} \in [0.0, 1.0]$$

- **`price_score` $\ge 0.75$ ($z < -1.0$)**: Rẻ / Rất hời so với mặt bằng và tiện nghi tương đương.
- **`price_score` $\approx 0.50$ ($-1.0 \le z \le 1.0$)**: Giá hợp lý, sát kỳ vọng thị trường.
- **`price_score` $\le 0.25$ ($z > 1.0$)**: Đắt hơn mặt bằng chung.

---

## 🚀 3. Hướng Dẫn Sử Dụng

### 3.1. Huấn Luyện Lại Mô Hình
```powershell
.\.venv\Scripts\python.exe -m ml.train_price_model
```
Sau khi huấn luyện, model sẽ được lưu tại `ml/artifacts/rent_pipeline.joblib` và `ml/artifacts/guard.joblib`.

### 3.2. Sử Dụng Trong Code / ETL Pipeline
```python
from ml import RoomPriceEvaluator

evaluator = RoomPriceEvaluator()
result = evaluator.evaluate_single({
    "listing_id": "nhatot_123456",
    "price_vnd": 2800000,
    "area_m2": 25.0,
    "district": "Thành phố Thủ Đức",
    "ward": "Phường Linh Xuân",
    "room_type": "ROOM",
    "safety_score": 0.85,
    "amenity_overall": 0.80,
})
print(result["price_score"], result["verdict"])
```

Trong luồng ETL (`crawler`), chỉ cần bật cờ `--eval-price`:
```powershell
.\.venv\Scripts\python.exe -m crawler.etl.pipeline --eval-price --embed
```
