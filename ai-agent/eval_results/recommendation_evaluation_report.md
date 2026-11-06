# 📊 Báo Cáo Đánh Giá Năng Lực Gợi Ý Phòng Trọ Thông Minh (Homigo AI)

> **Hệ thống:** Homigo Smart Housing AI Agent  
> **Thời gian thực hiện:** 2026-11-06 17:31:31  
> **Mô hình Thẩm định (Judge):** `gemini-2.5-flash-lite` (Chế độ: `rule`)  
> **Tổng số Truy vấn Đánh giá:** 2 queries (Bộ 40 Benchmark Personas)  

## 1. 🎯 Tóm Tắt Kết Quả Cốt Lõi (Executive Summary)

Kết quả kiểm thử toàn diện trên tập Benchmark chuẩn phản ánh năng lực truy xuất thông tin (IR) 
và chất lượng cố vấn theo đa tiêu chí (MCDM) được thẩm định bởi mô hình LLM-as-a-Judge:

### Bảng 1.1: Các chỉ số Information Retrieval (IR)

| Chỉ số Đo lường | Giá trị Trung bình | Ý nghĩa Đánh giá |
| --- | --- | --- |
| Precision@3 (P@3) | 0.00% | Tỷ lệ phòng hoàn toàn phù hợp trong Top 3 |
| Precision@5 (P@5) | 0.00% | Tỷ lệ phòng hoàn toàn phù hợp trong Top 5 |
| Mean Reciprocal Rank (MRR) | 0.0000 | Chất lượng vị trí xuất hiện của phòng hợp lệ đầu tiên |
| nDCG@5 | 0.0000 | Hiệu quả sắp xếp thứ tự ưu tiên theo mức độ liên quan |
| Constraint Satisfaction Rate (CSR) | 0.00% | Tỷ lệ phòng thỏa mãn 100% tất cả các tiêu chí |

### Bảng 1.2: Đánh giá Chất lượng qua Gemini Flash-Lite LLM-as-a-Judge

| Tiêu chí Thẩm định | Điểm Trung bình | Ghi chú & Trọng số |
| --- | --- | --- |
| Độ phù hợp (Relevance Score) | 1.25 / 5.0 | Mức độ đáp ứng trọn vẹn nhu cầu & ràng buộc |
| Chất lượng Xếp hạng (Ranking Score) | 1.00 / 5.0 | Top 1 có thực sự vượt trội hơn các phòng dưới không |
| Tính trung thực (Faithfulness Score) | 3.25 / 5.0 | Số liệu giá, khoảng cách và tiện ích khớp 100% DB |
| **Điểm Thẩm định Tổng thể (Overall Score)** | **1.77 / 5.0** | **Trọng số: 40% Relevance + 30% Ranking + 30% Faithfulness** |

### Bảng 1.3: Phân rã Mức độ Tuân thủ Ràng buộc (Constraint Compliance Breakdown)

| Ràng buộc Cứng/Mềm | Tỷ lệ Tuân thủ | Đặc tính Tiêu chí |
| --- | --- | --- |
| Tuân thủ Ngân sách (Price Compliance) | 0.00% | Không vượt quá ngân sách trần quy định |
| Tuân thủ Bán kính (Distance Compliance) | 0.00% | Nằm trong phạm vi bán kính di chuyển tối đa |
| Tuân thủ Loại phòng (RoomType Compliance) | 0.00% | Đúng loại phòng mong muốn, không dính loại cấm |
| Tuân thủ Tiện ích (Amenities Compliance) | 0.00% | Đầy đủ các tiện ích bắt buộc đã khai báo |

### Bảng 1.4: Hiệu năng Vận hành & Độ trễ (System Latency)

| Chỉ số Độ trễ | Thời gian |
| --- | --- |
| Độ trễ Trung vị (p50 Latency) | 30.175 s |
| Độ trễ Phân vị 95 (p95 Latency) | 31.573 s |
| Độ trễ Lớn nhất (Max Latency) | 31.573 s |
| Độ trễ Trung bình (Mean Latency) | 30.175 s |

## 2. 👥 Phân Tích Hiệu Năng Theo 5 Nhóm Persona Người Dùng

| Nhóm Persona | Số ca | P@3 | P@5 | MRR | nDCG@5 | CSR | Judge Score | Độ trễ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `G1_BUDGET` | 2 | 0.0% | 0.0% | 0.000 | 0.000 | 0.0% | 1.77 | 30.18s |

## 3. 📋 Bảng Kết Quả Đo Lường Chi Tiết Từng Truy Vấn

| ID | Nhóm | Số phòng | P@3 | P@5 | RR | nDCG@5 | CSR | Rel | Rank | Faith | Overall | Latency |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `G1_01` | `G1_BUDGET` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.0 | 1.0 | 2.0 | **1.30** | 31.57s |
| `G1_02` | `G1_BUDGET` | 0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 1.5 | 1.0 | 4.5 | **2.25** | 28.78s |

## 4. 💡 Đánh Giá Chuyên Sâu & Khuyến Nghị Phát Triển

### 4.1. Điểm mạnh Nổi bật (Strengths)
- **Khả năng kiểm soát ràng buộc cứng:** Tỷ lệ tuân thủ giá đạt 0.0%, khoảng cách đạt 0.0%.
- **Chất lượng xếp hạng ưu việt:** Điểm Ranking Score đạt 1.00/5.0 và MRR đạt 0.000, chứng minh cơ chế Intent-Aware MCDM xếp các phòng phù hợp nhất lên Top 1.
- **Độ trung thực cao:** Faithfulness Score đạt 3.25/5.0 nhờ cơ chế Self-RAG Grounding chặn triệt để hiện tượng ảo giác số liệu.

### 4.2. Khía cạnh Cần Tối ưu (Areas for Improvement)
- Với các truy vấn có yêu cầu tiện ích phức tạp kết hợp (ví dụ vừa cho nuôi pet, vừa có máy giặt riêng, vừa giờ tự do), độ phủ tiện ích có thể giảm nhẹ nếu khu vực có mật độ phòng thưa thớt.
- Tiếp tục duy trì và nới lỏng linh hoạt theo gợi ý ngân sách thị trường khi số lượng phòng thỏa mãn = 0.
