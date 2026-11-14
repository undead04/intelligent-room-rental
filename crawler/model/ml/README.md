# 🧠 ML Module — Conformal Prediction & Room Price Evaluator v2 (`crawler/model/ml/`)

Module **Machine Learning (`crawler/model/ml/`)** chịu trách nhiệm huấn luyện và suy luận mô hình thẩm định mức độ hợp lý của giá thuê phòng trọ (**`price_score`**) trên phạm vi **Toàn Quốc (24+ tỉnh/thành phố)** và **Đa phân khúc phòng (5 loại phòng)**. Thay vì sử dụng phép chia thô `price_per_m2` (vốn sai lệch nặng khi phòng diện tích nhỏ, phòng Studio full nội thất, hoặc phòng Ký túc xá / Sleepbox / Ở ghép), hệ thống dự đoán khoảng giá hợp lý $[P_{\text{low}}, P_{\text{high}}]$ theo từng phân khúc và quy đổi thành điểm số chuẩn hóa `price_score` $\in [0.0, 1.0]$.

---

## 📂 1. Cấu Trúc Thư Mục

```text
crawler/model/ml/
├── __init__.py                  # Export PriceEvaluator / RoomPriceEvaluator
├── feature_extractor.py         # Trích xuất 26 đặc trưng Toàn Quốc + Bộ lọc thích ứng theo RoomType
├── models.py                    # LightGBM + XGBoost Blend, Weighted SpatialTE, Mondrian CQR & InputGuard
├── price_evaluator.py           # Service suy luận (Inference) tính price_score theo lô/đơn lẻ
├── train_price_model.py         # Script huấn luyện Optuna 5-Fold Stratified CV & xuất artifacts
├── evaluate_model.py            # Script EDA, giải trình chọn đặc trưng (Ablation) & đánh giá mô hình
└── artifacts/                   # Thư mục lưu model & báo cáo đánh giá
    ├── rent_pipeline.joblib     # Trọng số ensemble (LightGBM + XGBoost) & MondrianPriceInterval
    ├── guard.joblib             # Bộ lọc ngoại lai InputGuard Toàn Quốc thích ứng theo loại phòng
    ├── training_metrics.json    # Tóm tắt chỉ số khi train (MAE, RMSE, R², Conformal Coverage)
    ├── evaluation_report.json   # Số liệu chi tiết EDA, Feature Importance, Ablation & Segment Eval
    └── evaluation_report.md     # Báo cáo phân tích & đánh giá trực quan tiếng Việt
```

*(Danh mục tọa độ 48 trung tâm đô thị & 50 cụm đại học lớn trên toàn quốc được tách độc lập tại [`crawler/config/poi_locations.json`](../../config/poi_locations.json)).*

---

## ⚙️ 2. Cơ Sở Toán Học & Thuật Toán (v2)

### 2.1. Tập 19 Đặc Trưng Cốt Lõi Tinh Gọn Cho Mô Hình ML (`feature_extractor.py`)
Mỗi tin đăng được trích xuất thành vector 19 đặc trưng cốt lõi (sau khi tinh gọn, loại bỏ 7 cờ quy định & an ninh có gain cận 0 không đóng góp cho bài toán định giá tiền thuê):
1. **Quy mô & Phân khúc (5 features):** `area_m2`, `lat`, `lng`, `room_type_id` (`1: ROOM`, `2: STUDIO`, `3: APARTMENT`, `4: SLEEPBOX`, `5: WHOLE_HOUSE`), `furnishing_code`.
2. **Nội thất & Tiện nghi cốt lõi (10 cờ nhị phân):**
   - **8 Tiện ích & Nội thất cấu thành chi phí thuê:** `is_furniture`, `is_aircon`, `is_window_balcony`, `is_elevator`, `is_mezzanine`, `is_private_wc`, `is_fridge`, `is_washing_machine`.
   - **2 Quy định & An ninh trọng yếu:** `is_free_hours`, `is_guard`.
   *(7 cờ `is_kitchen`, `is_parking`, `is_no_shared_landlord`, `is_pet_allowed`, `is_fingerprint_lock`, `is_camera`, `is_safe_area` vẫn được lưu trữ và sử dụng đầy đủ ở tầng Database/Backend để phục vụ bộ lọc tìm kiếm người dùng và AI Agent).*
3. **Điểm Ngữ Nghĩa LLM (2 features):** `amenity_overall` $\in [0.0, 1.0]$ và `safety_score` $\in [0.0, 1.0]$ (tổng hợp ngữ nghĩa toàn diện từ LLM).
4. **Khoảng Cách Haversine Đa Trung Tâm Đô Thị & Đại Học (2 features):** `dist_nearest_hub_km` (đến 48 trung tâm hành chính/thương mại) và `dist_nearest_uni_km` (đến 50 cụm đại học lớn).

### 2.2. Đặc Trưng Phái Sinh & `SpatialTE` Trọng Số Khoảng Cách (`models.py`)
- **`make_base_features`:** Tính mật độ tiện nghi trên quy mô diện tích `amenity_density = amenity_overall / ln(1 + area_m2)` và tương quan tọa độ phẳng `lat_lng_sum`, `lat_lng_diff` (đã loại bỏ các biến đa cộng tuyến `log_area` và `n_amenities`).
- **Inverse-Distance Weighted `SpatialTE`:** Sử dụng `BallTree(metric="haversine")` tìm $k \in \{5, 20\}$ phòng láng giềng gần nhất và tính trung bình có trọng số nghịch đảo khoảng cách $w_j = \frac{1}{1 + d_j(\text{km})}$ (`nb5_logy_mean`, `nb5_logppm_mean`, `nb20_logy_mean`, `nb20_logppm_mean`, `nb5_dist_km`, `nb20_dist_km`, `nb20_logy_std`), đồng thời loại bỏ chính điểm đang xét trong `transform_train` để chống rò rỉ dữ liệu 100%.

### 2.3. Ensemble, Mondrian Conformal Prediction & `InputGuard` Toàn Quốc
1. **Dự đoán giá kỳ vọng ($P_{\text{mid}}$):** Kết hợp (Blend) giữa **LightGBM** và **XGBoost** được tối ưu siêu tham số qua **Optuna 5-Fold Stratified CV** trên không gian logarit $\ln(1 + P)$ kèm hệ số hiệu chỉnh chệch bình phương tối thiểu (Least-Squares Smearing Calibration).
2. **Dự đoán khoảng tin cậy ($[P_{\text{low}}, P_{\text{high}}]$):** Áp dụng **Mondrian Conformal Prediction** (`MondrianPriceInterval`, `n_bins=5`, độ phủ danh định $80\%$) phân tầng theo mức giá dự đoán.
3. **`InputGuard` Toàn Quốc & Thích Ứng Theo `room_type_id`:** Hỗ trợ toàn lãnh thổ Việt Nam ($\text{lat} \in [8.0, 23.5]$, $\text{lng} \in [102.0, 110.0]$) và áp dụng bảng ngưỡng diện tích/giá/đơn giá (`ppm`) riêng biệt cho từng loại phòng (bảo vệ phân khúc `SLEEPBOX`/KTX/ở ghép có $\text{ppm} \ge 5.000\ \text{đ/m}^2$ và `WHOLE_HOUSE` diện tích lớn).

### 2.4. Kết Quả Thực Nghiệm (Tập Dữ Liệu Toàn Quốc `N = 9.693` Bản Ghi Sạch)

| Chỉ Số Đánh Giá (Trên Tập Test Độc Lập 15%) | Mô Hình v1 (1.249 mẫu) | Mô Hình v2 (9.693 mẫu - 19 Features) | Mức Cải Thiện |
| :--- | :---: | :---: | :---: |
| **MAE (Sai số tuyệt đối trung bình)** | $1.004.361\ \text{VNĐ}$ | **$599.687\ \text{VNĐ}$** | **$-40,3\%$ sai số** |
| **RMSE (Sai số toàn phương trung bình)** | $1.499.317\ \text{VNĐ}$ | **$860.175\ \text{VNĐ}$** | **$-42,6\%$ sai số** |
| **$R^2$ Score (Không gian tiền tệ VNĐ)** | $0.3111$ | **$0.6659$** | **Tăng $\times 2,14$ lần (+35,48 điểm %)** |
| **$R^2$ Score (Không gian Log-Price)** | — | **$0.7220$** | Giải thích $> 72,2\%$ phương sai |
| **Conformal Coverage Thực Tế (Kỳ vọng 80%)** | $79,3\%$ | **$82,5\%$** | Đạt chuẩn $[78\%, 85\%]$ |

### 2.5. Phân Tích Dữ Liệu (EDA), Giải Trình Đặc Trưng & Đánh Giá Chi Tiết
Xem báo cáo đầy đủ được sinh tự động tại [`artifacts/evaluation_report.md`](./artifacts/evaluation_report.md) và [`artifacts/evaluation_report.json`](./artifacts/evaluation_report.json):
- **Phễu làm sạch (EDA Funnel):** Từ **10.430** tin gốc $\rightarrow$ loại **3** tin lỗi tọa độ ngoài Việt Nam (`10.427`) $\rightarrow$ loại **734** tin ngoài ngưỡng diện tích/giá/đơn giá theo từng loại phòng $\rightarrow$ **9.693 tin sạch (92,93%)**. Phân bố gồm `ROOM` (5.940 - 61,28%), `STUDIO` (2.114 - 21,81%), `APARTMENT` (1.174 - 12,11%), `SLEEPBOX` (351 - 3,62%) và `WHOLE_HOUSE` (114 - 1,18%).
- **Lý do chọn 19 Features + `SpatialTE` (29 cột vào cây):**
  - `area_m2` vs `log_area` có $\text{Spearman} = 1.0000$; `n_amenities` vs `amenity_overall` có $\text{Pearson} = 0.9462$ $\rightarrow$ Loại biến đa cộng tuyến, giữ `amenity_density`.
  - **7 cờ bị cắt (`PRUNED_LOW_IMPACT_FLAGS`)** đều có `Mutual Info <= 0.0107` và đã được tóm tắt trong `amenity_overall` (`is_kitchen`: $r = +0.726$) & `safety_score` (`is_camera`: $r = +0.742$, `is_fingerprint_lock`: $r = +0.720$).
  - **Ablation Study (Holdout Test 15%, zero-leakage):** Cấu hình `4_Pruned_19_With_SpatialTE` (29 cột) đạt `MAE = 602.648 đ`, `R² = 0.6669`, **vượt trội** cả khi giữ đủ 26 đặc trưng (`MAE = 603.455 đ`, `R² = 0.6654`) và khi bỏ `SpatialTE` (`MAE = 604.912 đ`, `R² = 0.6625`).
  - **Top 5 Ensemble Gain (`rent_pipeline.joblib`):** `room_type_id` (25,00%), `area_m2` (18,39%), `is_furniture` (13,55%), `nb20_logy_mean` (7,62%), `furnishing_code` (3,92%).
- **So sánh Holdout 15% (1.454 mẫu) & Tổng quát hóa Toàn Quốc:**
  - `Baseline (Room-Type Median)`: `MAE = 944.079 đ`, `MdAPE = 20,93%`, `R² = 0.2510`.
  - `LightGBM`: `MAE = 600.658 đ`, `R² = 0.6667`, `R²_log = 0.7207`.
  - `XGBoost`: `MAE = 601.623 đ`, `R² = 0.6667`, `R²_log = 0.7219`.
  - **`Ensemble Blend (LGBM + XGB)`:** `MAE = 598.769 đ`, `MdAPE = 12,45%`, `RMSE = 856.392 đ`, **`R² = 0.6689`**, **`R²_log = 0.7235`**.
  - Theo địa lý: TP.HCM đạt `R² = 0.6638` (`83,2%` coverage) và Tỉnh/TP khác đạt `R² = 0.7083` (`83,0%` coverage). Mondrian Conformal toàn cục đạt **83,15%** (kỳ vọng 80%).

### 2.6. Công Thức Tính Điểm Hợp Lý Giá (`price_score`)
Trong không gian logarit $\ell(x) = \ln(1 + x)$:
$$\mu = \frac{\ell(P_{\text{low}}) + \ell(P_{\text{high}})}{2}, \quad \sigma = \max\left(\frac{\ell(P_{\text{high}}) - \ell(P_{\text{low}})}{2}, 10^{-6}\right)$$
$$z = \frac{\ell(P_{\text{actual}}) - \mu}{\sigma}$$
$$\text{PriceScore}_{100} = \text{clip}(50 - 25 \cdot z,\ 0,\ 100), \quad \text{PriceScore} = \frac{\text{PriceScore}_{100}}{100} \in [0.0, 1.0]$$

- **`price_score` $\ge 0.75$ ($z < -1.0$)**: Rẻ / Rất hời so với mặt bằng và tiện nghi tương đương.
- **`price_score` $\approx 0.50$ ($-1.0 \le z \le 1.0$)**: Giá hợp lý, sát kỳ vọng thị trường.
- **`price_score` $\le 0.25$ ($z > 1.0$)**: Đắt hơn mặt bằng chung.

---

## 🚀 3. Hướng Dẫn Sử Dụng

### 3.1. Trích Xuất Đặc Trưng, Phân Tích EDA & Đánh Giá / Huấn Luyện Mô Hình
```powershell
# 1. Kiểm tra trích xuất đặc trưng và cập nhật file cache Parquet
.\crawler\.venv\Scripts\python.exe -m crawler.model.ml.feature_extractor

# 2. Chạy phân tích EDA, giải trình chọn đặc trưng (Ablation) & đánh giá toàn diện mô hình
.\crawler\.venv\Scripts\python.exe -m crawler.model.ml.evaluate_model

# 3. Huấn luyện mô hình và xuất artifacts (.joblib, training_metrics.json)
.\crawler\.venv\Scripts\python.exe -m crawler.model.ml.train_price_model
```

### 3.2. Sử Dụng Trong Code / ETL Pipeline
```python
from crawler.model.ml import RoomPriceEvaluator

evaluator = RoomPriceEvaluator()
result = evaluator.evaluate_single({
    "listing_id": "nhatot_123456",
    "price_vnd": 3_200_000,
    "area_m2": 20.0,
    "lat": 10.772,
    "lng": 106.657,
    "room_type_id": 1,
    "aircon": True,
    "private_wc": True,
    "safety_score": 0.85,
    "amenity_overall": 0.80,
})
print(result["price_score"], result["verdict"], result["guard_status"])
```

Trong luồng ETL (`crawler`), chỉ cần bật cờ `--eval-price`:
```powershell
.\crawler\.venv\Scripts\python.exe -m crawler.etl.pipeline --eval-price --embed
```
