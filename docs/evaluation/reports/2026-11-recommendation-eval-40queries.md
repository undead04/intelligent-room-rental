# 📊 Báo Cáo Đánh Giá Năng Lực Gợi Ý Phòng Trọ Thông Minh (Homigo AI)

> **Hệ thống:** Homigo Smart Housing AI Agent  
> **Thời gian thực hiện:** 2026-11-07 12:05:31  
> **Mô hình Thẩm định (Judge):** `gemini-2.5-flash-lite` (Chế độ: `rule`)  
> **Tổng số Truy vấn Đánh giá:** 40 queries (Bộ 40 Benchmark Personas)  

## 1. 🎯 Tóm Tắt Kết Quả Cốt Lõi (Executive Summary)

Kết quả kiểm thử toàn diện trên tập Benchmark chuẩn phản ánh năng lực truy xuất thông tin (IR) 
và chất lượng cố vấn theo đa tiêu chí (MCDM) được thẩm định bởi mô hình LLM-as-a-Judge:

### Bảng 1.1: Các chỉ số Information Retrieval (IR)

| Chỉ số Đo lường | Giá trị Trung bình | Ý nghĩa Đánh giá |
| --- | --- | --- |
| Precision@3 (P@3) | 82.50% | Tỷ lệ phòng hoàn toàn phù hợp trong Top 3 |
| Precision@5 (P@5) | 76.00% | Tỷ lệ phòng hoàn toàn phù hợp trong Top 5 |
| Mean Reciprocal Rank (MRR) | 0.8750 | Chất lượng vị trí xuất hiện của phòng hợp lệ đầu tiên |
| nDCG@5 | 0.8750 | Hiệu quả sắp xếp thứ tự ưu tiên theo mức độ liên quan |
| Constraint Satisfaction Rate (CSR) | 87.50% | Tỷ lệ phòng thỏa mãn 100% tất cả các tiêu chí |

### Bảng 1.2: Đánh giá Chất lượng qua Gemini Flash-Lite LLM-as-a-Judge

| Tiêu chí Thẩm định | Điểm Trung bình | Ghi chú & Trọng số |
| --- | --- | --- |
| Độ phù hợp (Relevance Score) | 4.50 / 5.0 | Mức độ đáp ứng trọn vẹn nhu cầu & ràng buộc |
| Chất lượng Xếp hạng (Ranking Score) | 4.32 / 5.0 | Top 1 có thực sự vượt trội hơn các phòng dưới không |
| Tính trung thực (Faithfulness Score) | 4.62 / 5.0 | Số liệu giá, khoảng cách và tiện ích khớp 100% DB |
| **Điểm Thẩm định Tổng thể (Overall Score)** | **4.48 / 5.0** | **Trọng số: 40% Relevance + 30% Ranking + 30% Faithfulness** |

### Bảng 1.3: Phân rã Mức độ Tuân thủ Ràng buộc (Constraint Compliance Breakdown)

| Ràng buộc Cứng/Mềm | Tỷ lệ Tuân thủ | Đặc tính Tiêu chí |
| --- | --- | --- |
| Tuân thủ Ngân sách (Price Compliance) | 87.50% | Không vượt quá ngân sách trần quy định |
| Tuân thủ Bán kính (Distance Compliance) | 87.50% | Nằm trong phạm vi bán kính di chuyển tối đa |
| Tuân thủ Loại phòng (RoomType Compliance) | 87.50% | Đúng loại phòng mong muốn, không dính loại cấm |
| Tuân thủ Tiện ích (Amenities Compliance) | 87.50% | Đầy đủ các tiện ích bắt buộc đã khai báo |

### Bảng 1.4: Hiệu năng Vận hành & Độ trễ (System Latency)

| Chỉ số Độ trễ | Thời gian |
| --- | --- |
| Độ trễ Trung vị (p50 Latency) | 0.124 s |
| Độ trễ Phân vị 95 (p95 Latency) | 0.366 s |
| Độ trễ Lớn nhất (Max Latency) | 2.606 s |
| Độ trễ Trung bình (Mean Latency) | 0.200 s |

## 2. 👥 Phân Tích Hiệu Năng Theo 5 Nhóm Persona Người Dùng

| Nhóm Persona | Số ca | P@3 | P@5 | MRR | nDCG@5 | CSR | Judge Score | Độ trễ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `G1_BUDGET` | 8 | 87.5% | 72.5% | 0.875 | 0.875 | 87.5% | 4.51 | 0.43s |
| `G2_SAFETY_AMENITY` | 8 | 100.0% | 100.0% | 1.000 | 1.000 | 100.0% | 4.91 | 0.18s |
| `G3_GROUP_FRIENDS` | 8 | 50.0% | 37.5% | 0.625 | 0.625 | 62.5% | 3.57 | 0.11s |
| `G4_PREMIUM_STUDIO` | 8 | 91.7% | 90.0% | 1.000 | 1.000 | 100.0% | 4.92 | 0.13s |
| `G5_EDGE_CASES` | 8 | 83.3% | 80.0% | 0.875 | 0.875 | 87.5% | 4.50 | 0.15s |

## 3. 📋 Bảng Kết Quả Đo Lường Chi Tiết Từng Truy Vấn

| ID | Nhóm | Số phòng | P@3 | P@5 | RR | nDCG@5 | CSR | Rel | Rank | Faith | Overall | Latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `G1_01` | `G1_BUDGET` | 3 | 1.00 | 0.60 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 2.61s |
| `G1_02` | `G1_BUDGET` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.15s |
| `G1_03` | `G1_BUDGET` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.13s |
| `G1_04` | `G1_BUDGET` | 3 | 1.00 | 0.60 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.13s |
| `G1_05` | `G1_BUDGET` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 0.13s |
| `G1_06` | `G1_BUDGET` | 3 | 1.00 | 0.60 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.11s |
| `G1_07` | `G1_BUDGET` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.10s |
| `G1_08` | `G1_BUDGET` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.12s |
| `G2_01` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.29s |
| `G2_02` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.12s |
| `G2_03` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.22s |
| `G2_04` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.14s |
| `G2_05` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.12s |
| `G2_06` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.13s |
| `G2_07` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.29s |
| `G2_08` | `G2_SAFETY_AMENITY` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.15s |
| `G3_01` | `G3_GROUP_FRIENDS` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.12s |
| `G3_02` | `G3_GROUP_FRIENDS` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 0.10s |
| `G3_03` | `G3_GROUP_FRIENDS` | 2 | 0.67 | 0.40 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.15s |
| `G3_04` | `G3_GROUP_FRIENDS` | 4 | 1.00 | 0.80 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.11s |
| `G3_05` | `G3_GROUP_FRIENDS` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 0.10s |
| `G3_06` | `G3_GROUP_FRIENDS` | 1 | 0.33 | 0.20 | 1.00 | 1.00 | 1.00 | 5.0 | 4.5 | 5.0 | **4.85** | 0.10s |
| `G3_07` | `G3_GROUP_FRIENDS` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 0.10s |
| `G3_08` | `G3_GROUP_FRIENDS` | 3 | 1.00 | 0.60 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.10s |
| `G4_01` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.13s |
| `G4_02` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.15s |
| `G4_03` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.12s |
| `G4_04` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.11s |
| `G4_05` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.11s |
| `G4_06` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.12s |
| `G4_07` | `G4_PREMIUM_STUDIO` | 1 | 0.33 | 0.20 | 1.00 | 1.00 | 1.00 | 5.0 | 4.5 | 5.0 | **4.85** | 0.10s |
| `G4_08` | `G4_PREMIUM_STUDIO` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.17s |
| `G5_01` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.13s |
| `G5_02` | `G5_EDGE_CASES` | 2 | 0.67 | 0.40 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.09s |
| `G5_03` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.11s |
| `G5_04` | `G5_EDGE_CASES` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 0.09s |
| `G5_05` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.15s |
| `G5_06` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.6 | 5.0 | **4.88** | 0.37s |
| `G5_07` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.10s |
| `G5_08` | `G5_EDGE_CASES` | 5 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 5.0 | 4.9 | 5.0 | **4.97** | 0.15s |

## 4. 💡 Đánh Giá Chuyên Sâu & Khuyến Nghị Phát Triển

### 4.1. Điểm mạnh Nổi bật (Strengths)
- **Khả năng kiểm soát ràng buộc cứng:** Tỷ lệ tuân thủ giá đạt 87.5%, khoảng cách đạt 87.5%.
- **Chất lượng xếp hạng ưu việt:** Điểm Ranking Score đạt 4.32/5.0 và MRR đạt 0.875, chứng minh cơ chế Intent-Aware MCDM xếp các phòng phù hợp nhất lên Top 1.
- **Độ trung thực cao:** Faithfulness Score đạt 4.62/5.0 nhờ cơ chế Self-RAG Grounding chặn triệt để hiện tượng ảo giác số liệu.

### 4.2. Khía cạnh Cần Tối ưu (Areas for Improvement)
- Với các truy vấn có yêu cầu tiện ích phức tạp kết hợp (ví dụ vừa cho nuôi pet, vừa có máy giặt riêng, vừa giờ tự do), độ phủ tiện ích có thể giảm nhẹ nếu khu vực có mật độ phòng thưa thớt.
- Tiếp tục duy trì và nới lỏng linh hoạt theo gợi ý ngân sách thị trường khi số lượng phòng thỏa mãn = 0.
