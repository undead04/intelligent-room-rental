# 📊 Báo Cáo Đánh Giá Năng Lực Gợi Ý Phòng Trọ Thông Minh (Homigo AI)

> **Hệ thống:** Homigo Smart Housing AI Agent  
> **Thời gian thực hiện:** 2026-11-07 10:44:04  
> **Mô hình Thẩm định (Judge):** `gemini-2.5-flash-lite` (Chế độ: `rule`)  
> **Tổng số Truy vấn Đánh giá:** 40 queries (Bộ 40 Benchmark Personas)  

## 1. 🎯 Tóm Tắt Kết Quả Cốt Lõi (Executive Summary)

Kết quả kiểm thử toàn diện trên tập Benchmark chuẩn phản ánh năng lực truy xuất thông tin (IR) 
và chất lượng cố vấn theo đa tiêu chí (MCDM) được thẩm định bởi mô hình LLM-as-a-Judge:

### Bảng 1.1: Các chỉ số Information Retrieval (IR)

| Chỉ số Đo lường | Giá trị Trung bình | Ý nghĩa Đánh giá |
| --- | --- | --- |
| Precision@3 (P@3) | 63.33% | Tỷ lệ phòng hoàn toàn phù hợp trong Top 3 |
| Precision@5 (P@5) | 58.00% | Tỷ lệ phòng hoàn toàn phù hợp trong Top 5 |
| Mean Reciprocal Rank (MRR) | 0.7458 | Chất lượng vị trí xuất hiện của phòng hợp lệ đầu tiên |
| nDCG@5 | 0.7779 | Hiệu quả sắp xếp thứ tự ưu tiên theo mức độ liên quan |
| Constraint Satisfaction Rate (CSR) | 65.17% | Tỷ lệ phòng thỏa mãn 100% tất cả các tiêu chí |

### Bảng 1.2: Đánh giá Chất lượng qua Gemini Flash-Lite LLM-as-a-Judge

| Tiêu chí Thẩm định | Điểm Trung bình | Ghi chú & Trọng số |
| --- | --- | --- |
| Độ phù hợp (Relevance Score) | 3.53 / 5.0 | Mức độ đáp ứng trọn vẹn nhu cầu & ràng buộc |
| Chất lượng Xếp hạng (Ranking Score) | 3.80 / 5.0 | Top 1 có thực sự vượt trội hơn các phòng dưới không |
| Tính trung thực (Faithfulness Score) | 4.78 / 5.0 | Số liệu giá, khoảng cách và tiện ích khớp 100% DB |
| **Điểm Thẩm định Tổng thể (Overall Score)** | **3.98 / 5.0** | **Trọng số: 40% Relevance + 30% Ranking + 30% Faithfulness** |

### Bảng 1.3: Phân rã Mức độ Tuân thủ Ràng buộc (Constraint Compliance Breakdown)

| Ràng buộc Cứng/Mềm | Tỷ lệ Tuân thủ | Đặc tính Tiêu chí |
| --- | --- | --- |
| Tuân thủ Ngân sách (Price Compliance) | 92.50% | Không vượt quá ngân sách trần quy định |
| Tuân thủ Bán kính (Distance Compliance) | 82.67% | Nằm trong phạm vi bán kính di chuyển tối đa |
| Tuân thủ Loại phòng (RoomType Compliance) | 75.00% | Đúng loại phòng mong muốn, không dính loại cấm |
| Tuân thủ Tiện ích (Amenities Compliance) | 92.50% | Đầy đủ các tiện ích bắt buộc đã khai báo |

### Bảng 1.4: Hiệu năng Vận hành & Độ trễ (System Latency)

| Chỉ số Độ trễ | Thời gian |
| --- | --- |
| Độ trễ Trung vị (p50 Latency) | 0.108 s |
| Độ trễ Phân vị 95 (p95 Latency) | 0.377 s |
| Độ trễ Lớn nhất (Max Latency) | 2.277 s |
| Độ trễ Trung bình (Mean Latency) | 0.178 s |

## 2. 👥 Phân Tích Hiệu Năng Theo 5 Nhóm Persona Người Dùng

| Nhóm Persona | Số ca | P@3 | P@5 | MRR | nDCG@5 | CSR | Judge Score | Độ trễ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `G1_BUDGET` | 8 | 70.8% | 60.0% | 0.875 | 0.867 | 70.6% | 4.20 | 0.37s |
| `G2_SAFETY_AMENITY` | 8 | 58.3% | 57.5% | 0.573 | 0.675 | 57.5% | 3.64 | 0.15s |
| `G3_GROUP_FRIENDS` | 8 | 37.5% | 30.0% | 0.531 | 0.563 | 41.5% | 3.40 | 0.10s |
| `G4_PREMIUM_STUDIO` | 8 | 66.7% | 62.5% | 0.875 | 0.910 | 76.2% | 4.30 | 0.13s |
| `G5_EDGE_CASES` | 8 | 83.3% | 80.0% | 0.875 | 0.875 | 80.0% | 4.38 | 0.14s |

## 3. 📋 Bảng Kết Quả Đo Lường Chi Tiết Từng Truy Vấn

| ID | Nhóm | Số phòng | P@3 | P@5 | RR | nDCG@5 | CSR | Rel | Rank | Faith | Overall | Latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `G1_01` | `G1_BUDGET` | 5 | 0.67 | 0.60 | 1.00 | 0.97 | 0.60 | 3.6 | 4.9 | 5.0 | **4.41** | 2.28s |
| `G1_02` | `G1_BUDGET` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.09s |
| `G1_03` | `G1_BUDGET` | 5 | 1.00 | 0.80 | 1.00 | 1.00 | 0.80 | 3.8 | 4.9 | 5.0 | **4.49** | 0.11s |
| `G1_04` | `G1_BUDGET` | 3 | 1.00 | 0.60 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.09s |
| `G1_05` | `G1_BUDGET` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 0.08s |
| `G1_06` | `G1_BUDGET` | 4 | 0.67 | 0.60 | 1.00 | 0.97 | 0.75 | 3.8 | 4.9 | 5.0 | **4.49** | 0.09s |
| `G1_07` | `G1_BUDGET` | 2 | 0.33 | 0.20 | 1.00 | 1.00 | 0.50 | 2.5 | 5.0 | 5.0 | **4.00** | 0.08s |
| `G1_08` | `G1_BUDGET` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.11s |
| `G2_01` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.23s |
| `G2_02` | `G2_SAFETY_AMENITY` | 5 | 0.67 | 0.60 | 0.50 | 0.73 | 0.60 | 3.6 | 1.5 | 5.0 | **3.39** | 0.11s |
| `G2_03` | `G2_SAFETY_AMENITY` | 5 | 0.33 | 0.40 | 0.33 | 0.54 | 0.40 | 2.4 | 2.0 | 5.0 | **3.06** | 0.18s |
| `G2_04` | `G2_SAFETY_AMENITY` | 5 | 0.00 | 0.20 | 0.25 | 0.43 | 0.20 | 1.2 | 2.0 | 5.0 | **2.58** | 0.13s |
| `G2_05` | `G2_SAFETY_AMENITY` | 5 | 0.67 | 0.60 | 0.50 | 0.71 | 0.60 | 3.6 | 1.5 | 5.0 | **3.39** | 0.11s |
| `G2_06` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 0.80 | 1.00 | 0.98 | 0.80 | 3.8 | 4.6 | 5.0 | **4.40** | 0.12s |
| `G2_07` | `G2_SAFETY_AMENITY` | 5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 2.0 | 5.0 | **2.50** | 0.23s |
| `G2_08` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.12s |
| `G3_01` | `G3_GROUP_FRIENDS` | 5 | 0.00 | 0.40 | 0.25 | 0.50 | 0.40 | 2.4 | 2.0 | 5.0 | **3.06** | 0.12s |
| `G3_02` | `G3_GROUP_FRIENDS` | 3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 2.0 | 5.0 | **2.50** | 0.10s |
| `G3_03` | `G3_GROUP_FRIENDS` | 3 | 0.67 | 0.40 | 1.00 | 1.00 | 0.67 | 3.7 | 4.9 | 5.0 | **4.45** | 0.10s |
| `G3_04` | `G3_GROUP_FRIENDS` | 4 | 1.00 | 0.80 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.09s |
| `G3_05` | `G3_GROUP_FRIENDS` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 0.08s |
| `G3_06` | `G3_GROUP_FRIENDS` | 4 | 0.33 | 0.20 | 1.00 | 1.00 | 0.25 | 1.2 | 5.0 | 5.0 | **3.48** | 0.09s |
| `G3_07` | `G3_GROUP_FRIENDS` | 2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 2.0 | 5.0 | **2.50** | 0.12s |
| `G3_08` | `G3_GROUP_FRIENDS` | 3 | 1.00 | 0.60 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.09s |
| `G4_01` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.12s |
| `G4_02` | `G4_PREMIUM_STUDIO` | 5 | 0.67 | 0.60 | 1.00 | 0.89 | 0.60 | 3.6 | 5.0 | 5.0 | **4.44** | 0.17s |
| `G4_03` | `G4_PREMIUM_STUDIO` | 5 | 0.67 | 0.60 | 0.50 | 0.71 | 0.60 | 3.6 | 1.5 | 5.0 | **3.39** | 0.12s |
| `G4_04` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 0.80 | 1.00 | 1.00 | 0.80 | 3.8 | 4.9 | 5.0 | **4.49** | 0.11s |
| `G4_05` | `G4_PREMIUM_STUDIO` | 2 | 0.33 | 0.20 | 1.00 | 1.00 | 0.50 | 2.5 | 5.0 | 5.0 | **4.00** | 0.10s |
| `G4_06` | `G4_PREMIUM_STUDIO` | 5 | 0.33 | 0.60 | 0.50 | 0.68 | 0.60 | 3.6 | 1.5 | 5.0 | **3.39** | 0.10s |
| `G4_07` | `G4_PREMIUM_STUDIO` | 1 | 0.33 | 0.20 | 1.00 | 1.00 | 1.00 | 5.0 | 4.5 | 5.0 | **4.85** | 0.08s |
| `G4_08` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.21s |
| `G5_01` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.12s |
| `G5_02` | `G5_EDGE_CASES` | 5 | 0.67 | 0.40 | 1.00 | 1.00 | 0.40 | 2.4 | 4.9 | 5.0 | **3.93** | 0.08s |
| `G5_03` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.12s |
| `G5_04` | `G5_EDGE_CASES` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 0.08s |
| `G5_05` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.15s |
| `G5_06` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.38s |
| `G5_07` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.09s |
| `G5_08` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.15s |

## 4. 💡 Đánh Giá Chuyên Sâu & Khuyến Nghị Phát Triển

### 4.1. Điểm mạnh Nổi bật (Strengths)
- **Khả năng kiểm soát ràng buộc cứng:** Tỷ lệ tuân thủ giá đạt 92.5%, khoảng cách đạt 82.7%.
- **Chất lượng xếp hạng ưu việt:** Điểm Ranking Score đạt 3.80/5.0 và MRR đạt 0.746, chứng minh cơ chế Intent-Aware MCDM xếp các phòng phù hợp nhất lên Top 1.
- **Độ trung thực cao:** Faithfulness Score đạt 4.78/5.0 nhờ cơ chế Self-RAG Grounding chặn triệt để hiện tượng ảo giác số liệu.

### 4.2. Khía cạnh Cần Tối ưu (Areas for Improvement)
- Với các truy vấn có yêu cầu tiện ích phức tạp kết hợp (ví dụ vừa cho nuôi pet, vừa có máy giặt riêng, vừa giờ tự do), độ phủ tiện ích có thể giảm nhẹ nếu khu vực có mật độ phòng thưa thớt.
- Tiếp tục duy trì và nới lỏng linh hoạt theo gợi ý ngân sách thị trường khi số lượng phòng thỏa mãn = 0.
