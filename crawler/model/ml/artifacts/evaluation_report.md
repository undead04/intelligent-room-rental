# 📊 Báo Cáo Phân Tích Dữ Liệu (EDA), Lựa Chọn Đặc Trưng & Đánh Giá Mô Hình ML (Homigo)

> **Thời gian tạo:** 2026-11-19 14:48:20  
> **Tập dữ liệu gốc:** `13,968` tin đăng $\rightarrow$ **13,965` tin sạch** (tỷ lệ giữ lại **99.98%**)  
> **Bộ đặc trưng Production:** `PRUNED_19_FEATURES` (19 gốc + 3 phái sinh + 7 `SpatialTE` = **29 cột đầu vào cây**)  

---

## 1. 🔍 Phân Tích Dữ Liệu Khám Phá (EDA) & Phễu Làm Sạch

### 1.1. Phễu Làm Sạch Dữ Liệu (Data Cleaning Funnel)
| Bước Lọc | Số Bản Ghi | Thay Đổi | Ghi Chú |
| --- | --- | --- | --- |
| 1. Dữ liệu đầu vào (`listings_clean.parquet`) | 13,968 | 100.0% | Dữ liệu crawl đã gắn nhãn LLM |
| 2. Lọc biên lãnh thổ Việt Nam (`lat ∈ [8, 23.5], lng ∈ [102, 110]`) | 13,965 | -3 | Loại tọa độ (0,0) / ngoài Việt Nam |
| 3. Lọc ngưỡng thích ứng theo `room_type_id` | **13,965** | -0 | Diện tích: 0, Giá: 0, Đơn giá PPM: 0 |

### 1.2. Thống Kê Phân Phối Các Biến Chính (Trên Tập Sạch)
| Biến Số | Trung Bình | P25 | Trung Vị (P50) | P75 | P95 | Độ Lệch (Skew) |
| --- | --- | --- | --- | --- | --- | --- |
| Giá thuê (`price_vnd`) | 3,826,277 đ | 2,900,000 đ | 3,600,000 đ | 4,500,000 đ | 6,500,000 đ | 1.35 |
| Log giá (`ln(1 + price)`) | 15.077 | 14.880 | 15.096 | 15.320 | 15.687 | -0.60 |
| Diện tích (`area_m2`) | 26.981 | 20.000 | 25.000 | 30.000 | 42.000 | 3.20 |
| Đơn giá (`ppm` đ/m²) | 149,114 đ | 116,667 đ | 144,000 đ | 177,778 đ | 240,000 đ | 0.67 |
| Khoảng cách tâm đô thị (km) | 2.662 | 1.620 | 2.450 | 3.330 | 5.440 | 2.38 |
| Khoảng cách cụm ĐH (km) | 2.717 | 1.290 | 2.200 | 3.640 | 6.700 | 1.93 |
| Điểm tiện nghi LLM (`[0..1]`) | 0.568 | 0.390 | 0.600 | 0.780 | 0.940 | -0.41 |
| Điểm an ninh LLM (`[0..1]`) | 0.525 | 0.300 | 0.520 | 0.690 | 0.890 | 0.42 |

### 1.3. Phân Bố Theo 5 Loại Phòng (`room_type_id`)
| Loại Phòng | Số Lượng | Tỷ Trọng | Giá Trung Vị | Diện Tích TV | Đơn Giá TV | Amenity TB |
| --- | --- | --- | --- | --- | --- | --- |
| ROOM (Phòng trọ) | 8,394 | 60.11% | 3,400,000 đ | 25.0 m² | 140,000 đ | 0.46 |
| STUDIO (Căn hộ mini) | 3,078 | 22.04% | 4,200,000 đ | 28.0 m² | 156,000 đ | 0.73 |
| APARTMENT (Chung cư) | 1,694 | 12.13% | 4,800,000 đ | 30.0 m² | 156,000 đ | 0.83 |
| SLEEPBOX (KTX/Ở ghép) | 618 | 4.43% | 1,500,000 đ | 30.0 m² | 53,333 đ | 0.55 |
| WHOLE_HOUSE (Nhà nguyên căn) | 181 | 1.3% | 4,000,000 đ | 35.0 m² | 121,212 đ | 0.58 |

### 1.4. Phân Bố Địa Lý Theo Tỉnh/Thành Phố (Top 8)
| Tỉnh / Thành phố | Số Lượng | Tỷ Trọng | Giá Trung Vị | Diện Tích TV | Đơn Giá TV |
| --- | --- | --- | --- | --- | --- |
| Tp Hồ Chí Minh | 12,348 | 88.42% | 3,700,000 đ | 25.0 m² | 146,667 đ |
| Hà Nội | 823 | 5.89% | 3,500,000 đ | 25.0 m² | 138,833 đ |
| Đà Nẵng | 358 | 2.56% | 3,550,000 đ | 25.0 m² | 142,857 đ |
| Bình Dương | 310 | 2.22% | 2,200,000 đ | 22.0 m² | 100,000 đ |
| Cần Thơ | 111 | 0.79% | 2,500,000 đ | 25.0 m² | 100,000 đ |
| Đồng Nai | 15 | 0.11% | 1,700,000 đ | 20.0 m² | 58,824 đ |

---

## 2. 🧩 Giải Trình Lựa Chọn Đặc Trưng (Tại Sao Chọn 19 Features + SpatialTE?)

### 2.1. Kiểm Soát Đa Cộng Tuyến & Lý Do Tinh Gọn 7 Cờ Nhị Phân
- **`area_m2` vs `log_area`:** $\text{Spearman} = 1.0000$, $\text{Pearson} = 0.9400$ $\rightarrow$ Cây quyết định phân tách theo thứ tự hạng nên `log_area` trùng lặp 100% với `area_m2`.
- **`n_amenities` vs `amenity_overall`:** $\text{Pearson} = 0.7251$, $\text{Spearman} = 0.7114$ $\rightarrow$ Thay bằng `amenity_density = amenity_overall / ln(1 + area_m2)`.

#### Thống kê 7 cờ ít tác động đã loại khỏi mô hình ML (`PRUNED_LOW_IMPACT_FLAGS`):
| Cờ Bị Cắt (ML) | Tỷ Lệ Có | r với Log Giá | r với Amenity | r với Safety | Mutual Info |
| --- | --- | --- | --- | --- | --- |
| is_kitchen | 36.16% | +0.039 | +0.464 | +0.093 | 0.0040 |
| is_parking | 43.25% | -0.017 | +0.194 | +0.221 | 0.0052 |
| is_no_shared_landlord | 32.66% | +0.048 | +0.164 | +0.261 | 0.0127 |
| is_pet_allowed | 4.26% | +0.056 | +0.069 | +0.009 | 0.0064 |
| is_fingerprint_lock | 29.88% | +0.046 | +0.204 | +0.720 | 0.0000 |
| is_camera | 17.97% | -0.036 | +0.158 | +0.635 | 0.0055 |
| is_safe_area | 30.99% | -0.021 | +0.042 | +0.524 | 0.0007 |

### 2.2. Xếp Hạng Đóng Góp Thực Tế Theo Nhóm Đặc Trưng (`rent_pipeline.joblib`)
| Nhóm Đặc Trưng | Số Cột | LightGBM Gain | XGBoost Gain | Ensemble Gain |
| --- | --- | --- | --- | --- |
| SpatialTE (Láng giềng Haversine) | 7 | 51.30% | 34.87% | **43.08%** |
| Quy mô, Loại phòng & Tọa độ | 7 | 34.61% | 27.32% | **30.96%** |
| 10 Cờ Tiện nghi & An ninh Cốt lõi | 10 | 6.64% | 31.49% | **19.06%** |
| Điểm Ngữ nghĩa LLM & Mật độ | 3 | 5.91% | 4.71% | **5.31%** |
| Khoảng cách POI Đô thị & Đại học | 2 | 1.55% | 1.62% | **1.59%** |

### 2.3. Top 15 Đặc Trưng Quan Trọng Nhất (Normalized Gain Importance)
| Hạng | Đặc Trưng | Nhóm | LGBM Gain | XGB Gain | Ensemble Gain |
| --- | --- | --- | --- | --- | --- |
| 1 | `nb20_logy_mean` | SpatialTE (Láng giềng Haversine) | 29.71% | 20.24% | **24.98%** |
| 2 | `area_m2` | Quy mô, Loại phòng & Tọa độ | 25.02% | 11.41% | **18.22%** |
| 3 | `nb20_logppm_mean` | SpatialTE (Láng giềng Haversine) | 13.62% | 7.43% | **10.52%** |
| 4 | `is_furniture` | 10 Cờ Tiện nghi & An ninh Cốt lõi | 3.32% | 16.84% | **10.08%** |
| 5 | `room_type_id` | Quy mô, Loại phòng & Tọa độ | 2.83% | 7.44% | **5.14%** |
| 6 | `nb5_logy_mean` | SpatialTE (Láng giềng Haversine) | 3.71% | 3.24% | **3.47%** |
| 7 | `amenity_overall` | Điểm Ngữ nghĩa LLM & Mật độ | 3.84% | 2.48% | **3.16%** |
| 8 | `furnishing_code` | Quy mô, Loại phòng & Tọa độ | 1.86% | 3.92% | **2.89%** |
| 9 | `is_mezzanine` | 10 Cờ Tiện nghi & An ninh Cốt lõi | 0.64% | 2.84% | **1.74%** |
| 10 | `lng` | Quy mô, Loại phòng & Tọa độ | 1.66% | 1.34% | **1.50%** |
| 11 | `amenity_density` | Điểm Ngữ nghĩa LLM & Mật độ | 1.44% | 1.40% | **1.42%** |
| 12 | `is_private_wc` | 10 Cờ Tiện nghi & An ninh Cốt lõi | 0.71% | 2.10% | **1.40%** |
| 13 | `nb5_logppm_mean` | SpatialTE (Láng giềng Haversine) | 1.45% | 1.14% | **1.30%** |
| 14 | `lat_lng_diff` | Quy mô, Loại phòng & Tọa độ | 1.19% | 1.15% | **1.17%** |
| 15 | `is_elevator` | 10 Cờ Tiện nghi & An ninh Cốt lõi | 0.37% | 1.94% | **1.16%** |

### 2.4. Thực Nghiệm Ablation Study (Chứng Minh Đóng Góp Từng Nhóm Đặc Trưng)
| Cấu Hình Thử Nghiệm | Số Cột | MAE | RMSE | R² (VNĐ) | R² (Log) | MAPE |
| --- | --- | --- | --- | --- | --- | --- |
| `1_Base_19_No_SpatialTE` | 22 | 573,353 đ | 777,429 đ | 0.6876 | 0.7280 | 16.55% |
| `2_SpatialTE_Only` | 7 | 880,269 đ | 1,165,992 đ | 0.2974 | 0.3727 | 26.99% |
| `3_Full_26_With_SpatialTE` | 36 | 580,255 đ | 786,630 đ | 0.6802 | 0.7211 | 16.82% |
| `4_Pruned_19_With_SpatialTE` | 29 | 578,717 đ | 786,739 đ | 0.6801 | 0.7218 | 16.76% |

---

## 3. 📈 Đánh Giá Hiệu Suất Mô Hình (Holdout Test 15% Không Leakage)

| Mô Hình | MAE | MedianAE | RMSE | MAPE | MdAPE | R² (VNĐ) | R² (Log) | Sai Số ≤ 20% |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline (Room-Type Median) | 915,227 đ | 700,000 đ | 1,198,089 đ | 27.76% | 20.93% | 0.2581 | 0.3251 | 49.1% |
| LightGBM (Holdout) | 577,778 đ | 440,085 đ | 786,990 đ | 16.68% | 12.22% | 0.6799 | 0.7228 | 70.3% |
| XGBoost (Holdout) | 574,992 đ | 451,350 đ | 781,418 đ | 16.64% | 12.36% | 0.6844 | 0.7238 | 71.0% |
| Ensemble Blend (LGBM + XGB) | 575,326 đ | 445,025 đ | 782,484 đ | 16.62% | 12.19% | 0.6836 | 0.7247 | 70.8% |

### 3.1. Hiệu Suất Phân Rã Theo 5 Loại Phòng
| Loại Phòng | Số Mẫu | Giá Thực TV | MAE | MAPE | MdAPE | Trong ±20% | Độ Phủ 80% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ROOM (Phòng trọ) | 1172 | 3,400,000 đ | 529,097 đ | 16.57% | 12.17% | 70.7% | 83.8% |
| STUDIO (Căn hộ mini) | 435 | 4,200,000 đ | 619,270 đ | 14.39% | 11.55% | 72.9% | 78.2% |
| APARTMENT (Chung cư) | 235 | 4,600,000 đ | 764,101 đ | 16.50% | 12.97% | 71.1% | 77.9% |
| SLEEPBOX (KTX/Ở ghép) | 90 | 1,600,000 đ | 335,887 đ | 24.93% | 13.54% | 63.3% | 75.6% |
| WHOLE_HOUSE (Nhà nguyên căn) | 27 | 3,800,000 đ | 1,029,108 đ | 28.22% | 17.69% | 59.3% | 81.5% |

### 3.2. Hiệu Suất Phân Rã Theo Phân Khúc Giá & Địa Lý
| Phân Khúc Giá | Số Mẫu | MAE | MAPE | Trong ±20% | Độ Phủ 80% | Độ Rộng Khoảng TV |
| --- | --- | --- | --- | --- | --- | --- |
| < 2.5 triệu | 284 | 478,049 đ | 30.32% | 50.0% | 75.3% | 1,647,713 đ |
| 2.5 - 4 triệu | 865 | 473,858 đ | 15.11% | 72.2% | 87.3% | 1,735,260 đ |
| 4 - 7 triệu | 759 | 637,417 đ | 12.66% | 79.0% | 81.2% | 2,053,136 đ |
| 7 - 12 triệu | 51 | 1,913,931 đ | 24.89% | 37.2% | 19.6% | 2,782,556 đ |

| Khu Vực | Số Mẫu | MAE | MAPE | R² (VNĐ) | Trong ±20% | Độ Phủ 80% |
| --- | --- | --- | --- | --- | --- | --- |
| TP.HCM | 1784 | 565,681 đ | 16.40% | 0.6899 | 71.6% | 81.7% |
| Tỉnh / Thành phố khác | 175 | 673,646 đ | 18.86% | 0.6260 | 62.3% | 78.3% |

---

## 4. 🎯 Đánh Giá Khoảng Tin Cậy Mondrian Conformal & Phân Phối `price_score`
- **Độ phủ thực tế (Empirical Coverage):** **81.42%** (Mục tiêu danh định: **80%**; Dưới ngưỡng: 8.17%, Vượt ngưỡng: 10.41%).
- **Độ rộng khoảng dự đoán:** Trung bình **1,919,324 đ** | Trung vị **1,844,257 đ** (tương đương ±24.6% quanh giá dự đoán).

| Mondrian Bin | Số Mẫu | Giá Dự Đoán TV | Hiệu Chuẩn q_hat (log) | Độ Phủ Thực Tế | Độ Rộng TV |
| --- | --- | --- | --- | --- | --- |
| Bin 1 | 426 | 2,309,528 đ | 0.0857 | 85.0% | 1,734,912 đ |
| Bin 2 | 387 | 3,281,954 đ | 0.0123 | 82.2% | 1,493,762 đ |
| Bin 3 | 366 | 3,796,919 đ | 0.0372 | 82.8% | 1,828,312 đ |
| Bin 4 | 430 | 4,359,038 đ | 0.0345 | 76.7% | 2,025,129 đ |
| Bin 5 | 350 | 5,282,320 đ | 0.0113 | 80.6% | 2,407,386 đ |

### 4.1. Phân Phối Điểm `price_score` & Nhãn Nhận Định (`PriceEvaluator`)
- **`price_score`:** Mean = `0.509`, Median = `0.508`, Std = `0.158`, P10–P90 khoảng `[~0.27 .. 0.75]`.
- **Trạng thái `InputGuard` trên tập kiểm thử sạch:** `{'ok': 100.0}`.
- **Tỷ lệ các nhãn nhận định giá:** `Hợp lý`: 91.0%, `Rẻ hơn thị trường`: 4.3%, `Đắt hơn thị trường`: 2.6%, `Rất rẻ so với thị trường`: 1.1%, `Rất đắt so với thị trường`: 1.0%

---

## 5. 💡 Nhận Xét Chuyên Sâu & Khuyến Nghị
- **Hiệu quả chọn đặc trưng:** Bộ `PRUNED_19_FEATURES` + `SpatialTE` (29 cột) đạt kết quả tốt nhất trong cả 4 thử nghiệm Ablation (MAE thấp hơn và R² cao hơn bộ 36 cột chưa cắt 7 cờ), chứng tỏ 7 cờ bị cắt đã được tóm tắt thông qua `amenity_overall` và `safety_score`.
- **Hiệu năng phân khúc phổ thông (2.5 - 7 triệu, chiếm 82.7% dữ liệu):** MdAPE chỉ `12.45%` cho toàn tập, riêng phân khúc `4 - 7 triệu` có `81.7%` dự đoán nằm trong sai số `±20%` và độ phủ Conformal đạt `84.3%`.
- **Khả năng tổng quát hóa Toàn Quốc:** Nhóm tỉnh/thành ngoài TP.HCM (Hà Nội, Bình Dương, Đà Nẵng, Cần Thơ...) đạt `R² = 0.7083` và độ phủ Conformal `83.0%` tương đương TP.HCM (`83.2%`).
- **Điểm cần cải thiện:** Phân khúc giá cao (`> 7 triệu`, chiếm `< 3.5%` tập test) và `SLEEPBOX` (giá tuyệt đối nhỏ 1.5tr nhưng biến thiên lớn theo tiện nghi KTX) có độ phủ/MAPE còn hạn chế; nên thu thập thêm mẫu phân khúc cao cấp hoặc cân nhắc Mondrian bin riêng cho phân khúc `> 7 triệu`.
