# 📊 Báo Cáo Phân Tích Dữ Liệu (EDA), Lựa Chọn Đặc Trưng & Đánh Giá Mô Hình ML (Homigo)

> **Thời gian tạo:** 2026-11-14 11:29:44  
> **Tập dữ liệu gốc:** `10,430` tin đăng $\rightarrow$ **9,693` tin sạch** (tỷ lệ giữ lại **92.93%**)  
> **Bộ đặc trưng Production:** `PRUNED_19_FEATURES` (19 gốc + 3 phái sinh + 7 `SpatialTE` = **29 cột đầu vào cây**)  

---

## 1. 🔍 Phân Tích Dữ Liệu Khám Phá (EDA) & Phễu Làm Sạch

### 1.1. Phễu Làm Sạch Dữ Liệu (Data Cleaning Funnel)
| Bước Lọc | Số Bản Ghi | Thay Đổi | Ghi Chú |
| --- | --- | --- | --- |
| 1. Dữ liệu đầu vào (`listings_clean.parquet`) | 10,430 | 100.0% | Dữ liệu crawl đã gắn nhãn LLM |
| 2. Lọc biên lãnh thổ Việt Nam (`lat ∈ [8, 23.5], lng ∈ [102, 110]`) | 10,427 | -3 | Loại tọa độ (0,0) / ngoài Việt Nam |
| 3. Lọc ngưỡng thích ứng theo `room_type_id` | **9,693** | -734 | Diện tích: 710, Giá: 22, Đơn giá PPM: 690 |

### 1.2. Thống Kê Phân Phối Các Biến Chính (Trên Tập Sạch)
| Biến Số | Trung Bình | P25 | Trung Vị (P50) | P75 | P95 | Độ Lệch (Skew) |
| --- | --- | --- | --- | --- | --- | --- |
| Giá thuê (`price_vnd`) | 3,826,347 đ | 2,900,000 đ | 3,700,000 đ | 4,500,000 đ | 6,500,000 đ | 1.07 |
| Log giá (`ln(1 + price)`) | 15.077 | 14.880 | 15.124 | 15.320 | 15.687 | -0.63 |
| Diện tích (`area_m2`) | 27.058 | 20.000 | 25.000 | 30.000 | 44.400 | 2.65 |
| Đơn giá (`ppm` đ/m²) | 148,853 đ | 116,667 đ | 144,000 đ | 177,778 đ | 240,000 đ | 0.64 |
| Khoảng cách tâm đô thị (km) | 2.677 | 1.610 | 2.450 | 3.310 | 5.440 | 3.41 |
| Khoảng cách cụm ĐH (km) | 2.786 | 1.290 | 2.200 | 3.590 | 6.710 | 11.52 |
| Điểm tiện nghi LLM (`[0..1]`) | 0.371 | 0.150 | 0.350 | 0.600 | 0.850 | 0.43 |
| Điểm an ninh LLM (`[0..1]`) | 0.200 | 0.000 | 0.150 | 0.400 | 0.700 | 1.02 |

### 1.3. Phân Bố Theo 5 Loại Phòng (`room_type_id`)
| Loại Phòng | Số Lượng | Tỷ Trọng | Giá Trung Vị | Diện Tích TV | Đơn Giá TV | Amenity TB |
| --- | --- | --- | --- | --- | --- | --- |
| ROOM (Phòng trọ) | 5,940 | 61.28% | 3,400,000 đ | 25.0 m² | 140,000 đ | 0.35 |
| STUDIO (Căn hộ mini) | 2,114 | 21.81% | 4,300,000 đ | 28.0 m² | 156,000 đ | 0.39 |
| APARTMENT (Chung cư) | 1,174 | 12.11% | 4,800,000 đ | 30.0 m² | 152,087 đ | 0.39 |
| SLEEPBOX (KTX/Ở ghép) | 351 | 3.62% | 1,500,000 đ | 30.0 m² | 50,000 đ | 0.53 |
| WHOLE_HOUSE (Nhà nguyên căn) | 114 | 1.18% | 3,800,000 đ | 35.0 m² | 121,717 đ | 0.31 |

### 1.4. Phân Bố Địa Lý Theo Tỉnh/Thành Phố (Top 8)
| Tỉnh / Thành phố | Số Lượng | Tỷ Trọng | Giá Trung Vị | Diện Tích TV | Đơn Giá TV |
| --- | --- | --- | --- | --- | --- |
| Tp Hồ Chí Minh | 8,814 | 90.93% | 3,700,000 đ | 25.0 m² | 145,436 đ |
| Hà Nội | 424 | 4.37% | 3,500,000 đ | 25.0 m² | 140,000 đ |
| Bình Dương | 139 | 1.43% | 2,500,000 đ | 25.0 m² | 100,000 đ |
| Đà Nẵng | 136 | 1.4% | 3,950,000 đ | 25.0 m² | 150,000 đ |
| Cần Thơ | 97 | 1.0% | 2,500,000 đ | 25.0 m² | 100,000 đ |
| Bà Rịa - Vũng Tàu | 15 | 0.15% | 2,800,000 đ | 25.0 m² | 104,167 đ |
| Lâm Đồng | 13 | 0.13% | 3,000,000 đ | 30.0 m² | 106,250 đ |
| Long An | 12 | 0.12% | 1,850,000 đ | 20.0 m² | 80,464 đ |

---

## 2. 🧩 Giải Trình Lựa Chọn Đặc Trưng (Tại Sao Chọn 19 Features + SpatialTE?)

### 2.1. Kiểm Soát Đa Cộng Tuyến & Lý Do Tinh Gọn 7 Cờ Nhị Phân
- **`area_m2` vs `log_area`:** $\text{Spearman} = 1.0000$, $\text{Pearson} = 0.9443$ $\rightarrow$ Cây quyết định phân tách theo thứ tự hạng nên `log_area` trùng lặp 100% với `area_m2`.
- **`n_amenities` vs `amenity_overall`:** $\text{Pearson} = 0.9462$, $\text{Spearman} = 0.9450$ $\rightarrow$ Thay bằng `amenity_density = amenity_overall / ln(1 + area_m2)`.

#### Thống kê 7 cờ ít tác động đã loại khỏi mô hình ML (`PRUNED_LOW_IMPACT_FLAGS`):
| Cờ Bị Cắt (ML) | Tỷ Lệ Có | r với Log Giá | r với Amenity | r với Safety | Mutual Info |
| --- | --- | --- | --- | --- | --- |
| is_kitchen | 35.92% | +0.036 | +0.726 | +0.102 | 0.0021 |
| is_parking | 44.12% | -0.022 | +0.267 | +0.235 | 0.0000 |
| is_no_shared_landlord | 33.31% | +0.039 | +0.102 | +0.248 | 0.0107 |
| is_pet_allowed | 4.45% | +0.051 | +0.046 | -0.002 | 0.0000 |
| is_fingerprint_lock | 31.07% | +0.030 | +0.140 | +0.720 | 0.0105 |
| is_camera | 18.36% | -0.037 | +0.165 | +0.742 | 0.0018 |
| is_safe_area | 30.95% | -0.021 | +0.052 | +0.448 | 0.0000 |

### 2.2. Xếp Hạng Đóng Góp Thực Tế Theo Nhóm Đặc Trưng (`rent_pipeline.joblib`)
| Nhóm Đặc Trưng | Số Cột | LightGBM Gain | XGBoost Gain | Ensemble Gain |
| --- | --- | --- | --- | --- |
| Quy mô, Loại phòng & Tọa độ | 7 | 62.94% | 45.24% | **54.09%** |
| 10 Cờ Tiện nghi & An ninh Cốt lõi | 10 | 9.64% | 36.02% | **22.83%** |
| SpatialTE (Láng giềng Haversine) | 7 | 22.51% | 13.82% | **18.16%** |
| Điểm Ngữ nghĩa LLM & Mật độ | 3 | 2.57% | 2.94% | **2.76%** |
| Khoảng cách POI Đô thị & Đại học | 2 | 2.34% | 1.97% | **2.16%** |

### 2.3. Top 15 Đặc Trưng Quan Trọng Nhất (Normalized Gain Importance)
| Hạng | Đặc Trưng | Nhóm | LGBM Gain | XGB Gain | Ensemble Gain |
| --- | --- | --- | --- | --- | --- |
| 1 | `room_type_id` | Quy mô, Loại phòng & Tọa độ | 26.70% | 23.30% | **25.00%** |
| 2 | `area_m2` | Quy mô, Loại phòng & Tọa độ | 25.95% | 10.83% | **18.39%** |
| 3 | `is_furniture` | 10 Cờ Tiện nghi & An ninh Cốt lõi | 6.48% | 20.62% | **13.55%** |
| 4 | `nb20_logy_mean` | SpatialTE (Láng giềng Haversine) | 9.92% | 5.32% | **7.62%** |
| 5 | `furnishing_code` | Quy mô, Loại phòng & Tọa độ | 2.62% | 5.21% | **3.92%** |
| 6 | `nb20_logppm_mean` | SpatialTE (Láng giềng Haversine) | 4.13% | 2.51% | **3.32%** |
| 7 | `lng` | Quy mô, Loại phòng & Tọa độ | 2.93% | 1.84% | **2.39%** |
| 8 | `nb20_logy_std` | SpatialTE (Láng giềng Haversine) | 2.27% | 1.23% | **1.75%** |
| 9 | `nb5_logy_mean` | SpatialTE (Láng giềng Haversine) | 2.00% | 1.43% | **1.71%** |
| 10 | `is_aircon` | 10 Cờ Tiện nghi & An ninh Cốt lõi | 0.48% | 2.78% | **1.63%** |
| 11 | `nb20_dist_km` | SpatialTE (Láng giềng Haversine) | 1.87% | 1.36% | **1.62%** |
| 12 | `lat_lng_diff` | Quy mô, Loại phòng & Tọa độ | 1.73% | 1.37% | **1.55%** |
| 13 | `lat_lng_sum` | Quy mô, Loại phòng & Tọa độ | 1.53% | 1.44% | **1.48%** |
| 14 | `is_window_balcony` | 10 Cờ Tiện nghi & An ninh Cốt lõi | 0.59% | 2.35% | **1.47%** |
| 15 | `lat` | Quy mô, Loại phòng & Tọa độ | 1.48% | 1.24% | **1.36%** |

### 2.4. Thực Nghiệm Ablation Study (Chứng Minh Đóng Góp Từng Nhóm Đặc Trưng)
| Cấu Hình Thử Nghiệm | Số Cột | MAE | RMSE | R² (VNĐ) | R² (Log) | MAPE |
| --- | --- | --- | --- | --- | --- | --- |
| `1_Base_19_No_SpatialTE` | 22 | 604,912 đ | 864,601 đ | 0.6625 | 0.7165 | 17.15% |
| `2_SpatialTE_Only` | 7 | 1,006,823 đ | 1,401,496 đ | 0.1132 | 0.1059 | 33.50% |
| `3_Full_26_With_SpatialTE` | 36 | 603,455 đ | 860,911 đ | 0.6654 | 0.7190 | 17.14% |
| `4_Pruned_19_With_SpatialTE` | 29 | 602,648 đ | 858,948 đ | 0.6669 | 0.7192 | 17.15% |

---

## 3. 📈 Đánh Giá Hiệu Suất Mô Hình (Holdout Test 15% Không Leakage)

| Mô Hình | MAE | MedianAE | RMSE | MAPE | MdAPE | R² (VNĐ) | R² (Log) | Sai Số ≤ 20% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline (Room-Type Median) | 944,079 đ | 700,000 đ | 1,287,992 đ | 28.45% | 20.93% | 0.2510 | 0.3121 | 49.2% |
| LightGBM (Holdout) | 600,658 đ | 451,639 đ | 859,262 đ | 17.02% | 12.47% | 0.6667 | 0.7207 | 70.3% |
| XGBoost (Holdout) | 601,623 đ | 451,914 đ | 859,154 đ | 17.04% | 12.45% | 0.6667 | 0.7219 | 70.3% |
| Ensemble Blend (LGBM + XGB) | 598,769 đ | 449,141 đ | 856,392 đ | 16.96% | 12.45% | 0.6689 | 0.7235 | 70.2% |

### 3.1. Hiệu Suất Phân Rã Theo 5 Loại Phòng
| Loại Phòng | Số Mẫu | Giá Thực TV | MAE | MAPE | MdAPE | Trong ±20% | Độ Phủ 80% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ROOM (Phòng trọ) | 891 | 3,400,000 đ | 536,768 đ | 17.15% | 12.61% | 70.2% | 84.2% |
| STUDIO (Căn hộ mini) | 317 | 4,200,000 đ | 629,752 đ | 14.27% | 11.99% | 76.0% | 83.9% |
| APARTMENT (Chung cư) | 176 | 4,800,000 đ | 937,735 đ | 18.97% | 12.32% | 64.8% | 77.3% |
| SLEEPBOX (KTX/Ở ghép) | 53 | 1,500,000 đ | 295,540 đ | 22.18% | 17.39% | 54.7% | 79.2% |
| WHOLE_HOUSE (Nhà nguyên căn) | 17 | 4,000,000 đ | 706,709 đ | 19.61% | 14.39% | 64.7% | 88.2% |

### 3.2. Hiệu Suất Phân Rã Theo Phân Khúc Giá & Địa Lý
| Phân Khúc Giá | Số Mẫu | MAE | MAPE | Trong ±20% | Độ Phủ 80% | Độ Rộng Khoảng TV |
| --- | --- | --- | --- | --- | --- | --- |
| < 2.5 triệu | 206 | 505,127 đ | 31.76% | 48.1% | 68.9% | 1,707,857 đ |
| 2.5 - 4 triệu | 635 | 492,429 đ | 15.63% | 70.5% | 90.7% | 1,749,028 đ |
| 4 - 7 triệu | 568 | 601,462 đ | 12.16% | 81.7% | 84.3% | 2,376,577 đ |
| 7 - 12 triệu | 42 | 2,232,801 đ | 26.99% | 21.4% | 28.6% | 3,891,118 đ |
| > 12 triệu | 3 | 6,151,285 đ | 50.20% | 0.0% | 0.0% | 5,369,588 đ |

| Khu Vực | Số Mẫu | MAE | MAPE | R² (VNĐ) | Trong ±20% | Độ Phủ 80% |
| --- | --- | --- | --- | --- | --- | --- |
| TP.HCM | 1360 | 596,834 đ | 16.67% | 0.6638 | 70.7% | 83.2% |
| Tỉnh / Thành phố khác | 94 | 626,774 đ | 21.12% | 0.7083 | 61.7% | 83.0% |

---

## 4. 🎯 Đánh Giá Khoảng Tin Cậy Mondrian Conformal & Phân Phối `price_score`
- **Độ phủ thực tế (Empirical Coverage):** **83.15%** (Mục tiêu danh định: **80%**; Dưới ngưỡng: 7.84%, Vượt ngưỡng: 9.01%).
- **Độ rộng khoảng dự đoán:** Trung bình **2,132,441 đ** | Trung vị **1,981,681 đ** (tương đương ±26.8% quanh giá dự đoán).

| Mondrian Bin | Số Mẫu | Giá Dự Đoán TV | Hiệu Chuẩn q_hat (log) | Độ Phủ Thực Tế | Độ Rộng TV |
| --- | --- | --- | --- | --- | --- |
| Bin 1 | 324 | 2,395,419 đ | 0.0662 | 85.5% | 1,711,962 đ |
| Bin 2 | 248 | 3,265,491 đ | 0.0090 | 78.2% | 1,459,849 đ |
| Bin 3 | 316 | 3,816,374 đ | 0.0333 | 80.7% | 1,839,605 đ |
| Bin 4 | 277 | 4,366,563 đ | 0.0692 | 85.9% | 2,320,381 đ |
| Bin 5 | 289 | 5,184,505 đ | 0.0665 | 84.8% | 2,812,733 đ |

### 4.1. Phân Phối Điểm `price_score` & Nhãn Nhận Định (`PriceEvaluator`)
- **`price_score`:** Mean = `0.491`, Median = `0.489`, Std = `0.174`, P10–P90 khoảng `[~0.23 .. 0.76]`.
- **Trạng thái `InputGuard` trên tập kiểm thử sạch:** `{'ok': 100.0}`.
- **Tỷ lệ các nhãn nhận định giá:** `Hợp lý`: 87.8%, `Đắt hơn thị trường`: 5.2%, `Rẻ hơn thị trường`: 3.9%, `Rất rẻ so với thị trường`: 1.6%, `Rất đắt so với thị trường`: 1.4%

---

## 5. 💡 Nhận Xét Chuyên Sâu & Khuyến Nghị
- **Hiệu quả chọn đặc trưng:** Bộ `PRUNED_19_FEATURES` + `SpatialTE` (29 cột) đạt kết quả tốt nhất trong cả 4 thử nghiệm Ablation (MAE thấp hơn và R² cao hơn bộ 36 cột chưa cắt 7 cờ), chứng tỏ 7 cờ bị cắt đã được tóm tắt thông qua `amenity_overall` và `safety_score`.
- **Hiệu năng phân khúc phổ thông (2.5 - 7 triệu, chiếm 82.7% dữ liệu):** MdAPE chỉ `12.45%` cho toàn tập, riêng phân khúc `4 - 7 triệu` có `81.7%` dự đoán nằm trong sai số `±20%` và độ phủ Conformal đạt `84.3%`.
- **Khả năng tổng quát hóa Toàn Quốc:** Nhóm tỉnh/thành ngoài TP.HCM (Hà Nội, Bình Dương, Đà Nẵng, Cần Thơ...) đạt `R² = 0.7083` và độ phủ Conformal `83.0%` tương đương TP.HCM (`83.2%`).
- **Điểm cần cải thiện:** Phân khúc giá cao (`> 7 triệu`, chiếm `< 3.5%` tập test) và `SLEEPBOX` (giá tuyệt đối nhỏ 1.5tr nhưng biến thiên lớn theo tiện nghi KTX) có độ phủ/MAPE còn hạn chế; nên thu thập thêm mẫu phân khúc cao cấp hoặc cân nhắc Mondrian bin riêng cho phân khúc `> 7 triệu`.
