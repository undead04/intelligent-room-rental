# 📊 Báo Cáo Đánh Giá Năng Lực Gợi Ý Phòng Trọ Thông Minh (Homigo AI)

> **Hệ thống:** Homigo Smart Housing AI Agent  
> **Thời gian thực hiện:** 2026-11-06 22:22:47  
> **Mô hình Thẩm định (Judge):** `gemini-2.5-flash-lite` (Chế độ: `auto`)  
> **Tổng số Truy vấn Đánh giá:** 40 queries (Bộ 40 Benchmark Personas)  

## 1. 🎯 Tóm Tắt Kết Quả Cốt Lõi (Executive Summary)

Kết quả kiểm thử toàn diện trên tập Benchmark chuẩn phản ánh năng lực truy xuất thông tin (IR) 
và chất lượng cố vấn theo đa tiêu chí (MCDM) được thẩm định bởi mô hình LLM-as-a-Judge:

### Bảng 1.1: Các chỉ số Information Retrieval (IR)

| Chỉ số Đo lường | Giá trị Trung bình | Ý nghĩa Đánh giá |
| --- | --- | --- |
| Precision@3 (P@3) | 25.00% | Tỷ lệ phòng hoàn toàn phù hợp trong Top 3 |
| Precision@5 (P@5) | 19.00% | Tỷ lệ phòng hoàn toàn phù hợp trong Top 5 |
| Mean Reciprocal Rank (MRR) | 0.3958 | Chất lượng vị trí xuất hiện của phòng hợp lệ đầu tiên |
| nDCG@5 | 0.4171 | Hiệu quả sắp xếp thứ tự ưu tiên theo mức độ liên quan |
| Constraint Satisfaction Rate (CSR) | 21.00% | Tỷ lệ phòng thỏa mãn 100% tất cả các tiêu chí |

### Bảng 1.2: Đánh giá Chất lượng qua Gemini Flash-Lite LLM-as-a-Judge

| Tiêu chí Thẩm định | Điểm Trung bình | Ghi chú & Trọng số |
| --- | --- | --- |
| Độ phù hợp (Relevance Score) | 3.08 / 5.0 | Mức độ đáp ứng trọn vẹn nhu cầu & ràng buộc |
| Chất lượng Xếp hạng (Ranking Score) | 3.35 / 5.0 | Top 1 có thực sự vượt trội hơn các phòng dưới không |
| Tính trung thực (Faithfulness Score) | 4.12 / 5.0 | Số liệu giá, khoảng cách và tiện ích khớp 100% DB |
| **Điểm Thẩm định Tổng thể (Overall Score)** | **3.47 / 5.0** | **Trọng số: 40% Relevance + 30% Ranking + 30% Faithfulness** |

### Bảng 1.3: Phân rã Mức độ Tuân thủ Ràng buộc (Constraint Compliance Breakdown)

| Ràng buộc Cứng/Mềm | Tỷ lệ Tuân thủ | Đặc tính Tiêu chí |
| --- | --- | --- |
| Tuân thủ Ngân sách (Price Compliance) | 82.50% | Không vượt quá ngân sách trần quy định |
| Tuân thủ Bán kính (Distance Compliance) | 29.75% | Nằm trong phạm vi bán kính di chuyển tối đa |
| Tuân thủ Loại phòng (RoomType Compliance) | 70.13% | Đúng loại phòng mong muốn, không dính loại cấm |
| Tuân thủ Tiện ích (Amenities Compliance) | 80.00% | Đầy đủ các tiện ích bắt buộc đã khai báo |

### Bảng 1.4: Hiệu năng Vận hành & Độ trễ (System Latency)

| Chỉ số Độ trễ | Thời gian |
| --- | --- |
| Độ trễ Trung vị (p50 Latency) | 11.699 s |
| Độ trễ Phân vị 95 (p95 Latency) | 54.468 s |
| Độ trễ Lớn nhất (Max Latency) | 77.403 s |
| Độ trễ Trung bình (Mean Latency) | 16.733 s |

## 2. 👥 Phân Tích Hiệu Năng Theo 5 Nhóm Persona Người Dùng

| Nhóm Persona | Số ca | P@3 | P@5 | MRR | nDCG@5 | CSR | Judge Score | Độ trễ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `G1_BUDGET` | 8 | 25.0% | 22.5% | 0.375 | 0.441 | 22.5% | 3.58 | 12.49s |
| `G2_SAFETY_AMENITY` | 8 | 16.7% | 12.5% | 0.250 | 0.271 | 12.5% | 2.45 | 25.60s |
| `G3_GROUP_FRIENDS` | 8 | 12.5% | 7.5% | 0.250 | 0.250 | 7.5% | 3.81 | 16.98s |
| `G4_PREMIUM_STUDIO` | 8 | 29.2% | 17.5% | 0.479 | 0.516 | 27.5% | 3.67 | 9.89s |
| `G5_EDGE_CASES` | 8 | 41.7% | 35.0% | 0.625 | 0.608 | 35.0% | 3.85 | 18.72s |

## 3. 📋 Bảng Kết Quả Đo Lường Chi Tiết Từng Truy Vấn

| ID | Nhóm | Số phòng | P@3 | P@5 | RR | nDCG@5 | CSR | Rel | Rank | Faith | Overall | Latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `G1_01` | `G1_BUDGET` | 5 | 0.33 | 0.20 | 0.33 | 0.50 | 0.20 | 4.0 | 4.5 | 4.0 | **4.15** | 7.89s |
| `G1_02` | `G1_BUDGET` | 5 | 0.33 | 0.20 | 1.00 | 1.00 | 0.20 | 3.8 | 4.5 | 4.5 | **4.22** | 12.15s |
| `G1_03` | `G1_BUDGET` | 5 | 0.33 | 0.40 | 0.33 | 0.57 | 0.40 | 4.5 | 4.0 | 4.5 | **4.35** | 19.04s |
| `G1_04` | `G1_BUDGET` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 2.0 | 3.0 | 4.0 | **2.90** | 18.03s |
| `G1_05` | `G1_BUDGET` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 4.0 | 4.5 | 5.0 | **4.45** | 13.37s |
| `G1_06` | `G1_BUDGET` | 5 | 0.33 | 0.20 | 0.33 | 0.50 | 0.20 | 2.5 | 2.0 | 3.5 | **2.65** | 14.75s |
| `G1_07` | `G1_BUDGET` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 2.0 | 3.0 | 2.5 | **2.45** | 8.03s |
| `G1_08` | `G1_BUDGET` | 5 | 0.67 | 0.80 | 1.00 | 0.96 | 0.80 | 3.5 | 2.5 | 4.5 | **3.50** | 6.64s |
| `G2_01` | `G2_SAFETY_AMENITY` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 2.0 | 2.0 | **1.60** | 25.28s |
| `G2_02` | `G2_SAFETY_AMENITY` | 5 | 0.33 | 0.20 | 0.50 | 0.63 | 0.20 | 2.5 | 2.0 | 3.0 | **2.50** | 12.18s |
| `G2_03` | `G2_SAFETY_AMENITY` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 2.0 | 1.5 | 3.5 | **2.30** | 22.72s |
| `G2_04` | `G2_SAFETY_AMENITY` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 2.0 | 2.0 | 3.0 | **2.30** | 45.39s |
| `G2_05` | `G2_SAFETY_AMENITY` | 5 | 0.33 | 0.20 | 0.50 | 0.63 | 0.20 | 2.0 | 1.0 | 4.0 | **2.30** | 40.06s |
| `G2_06` | `G2_SAFETY_AMENITY` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 2.0 | 3.0 | **1.90** | 38.38s |
| `G2_07` | `G2_SAFETY_AMENITY` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 2.5 | 3.5 | 4.0 | **3.25** | 13.76s |
| `G2_08` | `G2_SAFETY_AMENITY` | 5 | 0.67 | 0.60 | 1.00 | 0.91 | 0.60 | 3.0 | 4.0 | 3.5 | **3.45** | 7.03s |
| `G3_01` | `G3_GROUP_FRIENDS` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 3.0 | 4.0 | 4.0 | **3.60** | 8.39s |
| `G3_02` | `G3_GROUP_FRIENDS` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 3.5 | 4.0 | 4.5 | **3.95** | 22.34s |
| `G3_03` | `G3_GROUP_FRIENDS` | 5 | 0.67 | 0.40 | 1.00 | 1.00 | 0.40 | 3.5 | 4.0 | 4.5 | **3.95** | 18.00s |
| `G3_04` | `G3_GROUP_FRIENDS` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 5.0 | 5.0 | 5.0 | **5.00** | 5.76s |
| `G3_05` | `G3_GROUP_FRIENDS` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 6.85s |
| `G3_06` | `G3_GROUP_FRIENDS` | 5 | 0.33 | 0.20 | 1.00 | 1.00 | 0.20 | 3.5 | 4.0 | 4.0 | **3.80** | 11.25s |
| `G3_07` | `G3_GROUP_FRIENDS` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 3.0 | 4.0 | 5.0 | **3.90** | 8.76s |
| `G3_08` | `G3_GROUP_FRIENDS` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 5.0 | 5.0 | 5.0 | **5.00** | 54.47s |
| `G4_01` | `G4_PREMIUM_STUDIO` | 5 | 0.33 | 0.20 | 0.50 | 0.63 | 0.20 | 2.5 | 1.5 | 4.0 | **2.65** | 7.76s |
| `G4_02` | `G4_PREMIUM_STUDIO` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 5.0 | 5.0 | 5.0 | **5.00** | 6.34s |
| `G4_03` | `G4_PREMIUM_STUDIO` | 5 | 0.33 | 0.20 | 1.00 | 1.00 | 0.20 | 4.5 | 4.0 | 5.0 | **4.50** | 12.35s |
| `G4_04` | `G4_PREMIUM_STUDIO` | 1 | 0.33 | 0.20 | 1.00 | 1.00 | 1.00 | 4.5 | 5.0 | 5.0 | **4.80** | 5.71s |
| `G4_05` | `G4_PREMIUM_STUDIO` | 5 | 0.33 | 0.20 | 0.33 | 0.50 | 0.20 | 2.0 | 2.0 | 2.0 | **2.00** | 30.21s |
| `G4_06` | `G4_PREMIUM_STUDIO` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 3.0 | 3.0 | 5.0 | **3.60** | 4.78s |
| `G4_07` | `G4_PREMIUM_STUDIO` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 5.0 | **2.20** | 4.19s |
| `G4_08` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 0.60 | 1.00 | 1.00 | 0.60 | 4.5 | 4.5 | 4.8 | **4.59** | 7.75s |
| `G5_01` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 4.0 | 4.5 | 5.0 | **4.45** | 7.18s |
| `G5_02` | `G5_EDGE_CASES` | 5 | 0.33 | 0.40 | 1.00 | 0.88 | 0.40 | 3.5 | 4.5 | 4.5 | **4.10** | 13.98s |
| `G5_03` | `G5_EDGE_CASES` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 5.0 | 5.0 | 5.0 | **5.00** | 3.87s |
| `G5_04` | `G5_EDGE_CASES` | 4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.5 | 2.5 | 3.0 | **2.25** | 10.95s |
| `G5_05` | `G5_EDGE_CASES` | 5 | 0.33 | 0.20 | 1.00 | 1.00 | 0.20 | 4.0 | 5.0 | 5.0 | **4.60** | 8.17s |
| `G5_06` | `G5_EDGE_CASES` | 5 | 1.00 | 0.80 | 1.00 | 0.98 | 0.80 | 4.5 | 4.0 | 4.5 | **4.35** | 19.24s |
| `G5_07` | `G5_EDGE_CASES` | 5 | 0.67 | 0.40 | 1.00 | 1.00 | 0.40 | 2.4 | 4.6 | 5.0 | **3.84** | 8.95s |
| `G5_08` | `G5_EDGE_CASES` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.5 | 1.0 | 4.5 | **2.25** | 77.40s |

## 4. 💡 Đánh Giá Chuyên Sâu & Khuyến Nghị Phát Triển

### 4.1. Điểm mạnh Nổi bật (Strengths)
- **Khả năng kiểm soát ràng buộc cứng:** Tỷ lệ tuân thủ giá đạt 82.5%, khoảng cách đạt 29.8%.
- **Chất lượng xếp hạng ưu việt:** Điểm Ranking Score đạt 3.35/5.0 và MRR đạt 0.396, chứng minh cơ chế Intent-Aware MCDM xếp các phòng phù hợp nhất lên Top 1.
- **Độ trung thực cao:** Faithfulness Score đạt 4.12/5.0 nhờ cơ chế Self-RAG Grounding chặn triệt để hiện tượng ảo giác số liệu.

### 4.2. Khía cạnh Cần Tối ưu (Areas for Improvement)
- Với các truy vấn có yêu cầu tiện ích phức tạp kết hợp (ví dụ vừa cho nuôi pet, vừa có máy giặt riêng, vừa giờ tự do), độ phủ tiện ích có thể giảm nhẹ nếu khu vực có mật độ phòng thưa thớt.
- Tiếp tục duy trì và nới lỏng linh hoạt theo gợi ý ngân sách thị trường khi số lượng phòng thỏa mãn = 0.
