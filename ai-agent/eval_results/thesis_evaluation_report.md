# BÁO CÁO ĐÁNH GIÁ ĐỊNH LƯỢNG HỆ THỐNG AI AGENT (HOMIGO)
**Đơn vị:** Trường Đại học Công nghệ Thông tin (UIT - ĐHQG TP.HCM)
**Thời gian đánh giá:** 2026-11-06 18:47:14  
**Chế độ NLU:** Offline Deterministic (không gọi LLM)

## 1. Tổng kết

- **Điểm thô:** 93.0 / 93.0 điểm đã đo (độ phủ 93% của thang 100)
- **Điểm quy đổi thang 100:** **100.0**
- **Xếp loại:** **XUẤT SẮC (EXCELLENT) — tạm thời (có tiêu chí chưa đo)**
- **Nhận định (sinh tự động từ số liệu):** Điểm quy đổi 100.0/100 (độ phủ phép đo 93%) — xếp loại: XUẤT SẮC (EXCELLENT) — tạm thời (có tiêu chí chưa đo). Chế độ NLU: Offline Deterministic (không gọi LLM). Mọi tiêu chí đã đo đều đạt tối đa trên bộ ca hiện tại (không đồng nghĩa hệ thống không có lỗi ngoài bộ ca). Chưa đo: 1.1 Phân loại ý định (Intent Classification).

| Trụ cột | Trọng số | Điểm | Đã đo | Tỷ lệ |
| :--- | :---: | :---: | :---: | :---: |
| 1. NLU & Trạng thái Tích lũy (State Tracking) | 25 | 18.00 | 18 | 100.0% |
| 2. Dynamic MCDM & Độ liên quan Truy xuất (Retrieval) | 25 | 25.00 | 25 | 100.0% |
| 3. Self-RAG & Kiểm chứng Grounding (Faithfulness & Relevance) | 20 | 20.00 | 20 | 100.0% |
| 4. Hỗ trợ Ra Quyết định & Cố vấn (Decision Support) | 15 | 15.00 | 15 | 100.0% |
| 5. An toàn Hệ thống & Hiệu năng Vận hành (Safety & Efficiency) | 15 | 15.00 | 15 | 100.0% |

## 2. Chi tiết từng tiêu chí

### Trụ cột 1: NLU & Trạng thái Tích lũy (State Tracking) (18.00/18 đã đo)

| Tiêu chí | Tối đa | Đạt | N | CI 95% | Trạng thái | Chi tiết |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| 1.1 Phân loại ý định (Intent Classification) | 7 | 0.00 | – | – | ⏭️ SKIP | CHƯA ĐO: Cần LLM (--with-model) để đo phân loại ý định NLU từ câu thô (hệ thống không dùng bộ đoán từ khoá). |
| 1.2 Trích xuất thực thể & ràng buộc (Entity Extraction) | 10 | 10.00 | 31 | 89–100% | ✅ PASS | Đúng 31/31 — tiền 9/9, diện tích 4/4, loại phòng 4/4, tiện ích 10/10, apply_patch 4/4 |
| 1.3 Session store: snapshot & rollback tiêu chí | 8 | 8.00 | 3 | – | ✅ PASS | ✔ Ghi đủ 3 snapshot | ✔ Thứ tự & giá trị từng snapshot đúng (gồm snapshot đầu có thể rollback) | ✔ Snapshot cách ly khỏi sửa đổi về sau của đối tượng gốc — Đây là test của session store, chưa phải test NLU gộp state đa lượt |

### Trụ cột 2: Dynamic MCDM & Độ liên quan Truy xuất (Retrieval) (25.00/25 đã đo)

| Tiêu chí | Tối đa | Đạt | N | CI 95% | Trạng thái | Chi tiết |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| 2.1 Trọng số động theo ý định (Intent-Aware MCDM) | 10 | 10.00 | 6 | 61–100% | ✅ PASS | Đúng 6/6. Tiêu chí: Priorities → apply_priorities → chuẩn hoá L1, không âm, yếu tố ưu tiên tăng ≥ 5% so với baseline, quy tắc động bật/tắt location & amenity chuẩn xác |
| 2.2 Cổng ràng buộc cứng sau truy xuất (Hard Constraints) | 9 | 9.00 | 7 | 65–100% | ✅ PASS | Đúng 7/7 phòng. Đo cổng lọc cuối (verify_context_grounding: ngân sách chặt, diện tích tối thiểu, loại hình bị cấm, ca biên). KHÔNG đo chất lượng xếp hạng/recall của truy xuất; dung sai ngân sách (nếu có) thuộc tầng retrieval. |
| 2.3 Độ đúng của hàm khoảng cách Haversine | 6 | 6.00 | 6 | – | ✅ PASS | ✔ d(A,A) = 0 | ✔ Đối xứng d(A,B) = d(B,A) | ✔ 1° vĩ độ ≈ 111.2 km (±0.5%) | ✔ UIT→KTX khớp cài đặt tham chiếu (±0.5%) | ✔ UIT→Bách Khoa khớp cài đặt tham chiếu (±0.5%) | ✔ Bất đẳng thức tam giác UIT→BK ≤ UIT→KTX + KTX→BK — UIT→KTX 2.58 km, →Chợ Linh Trung 3.61 km, →ĐH Bách Khoa 19.22 km. Đây là test hàm tiện ích, không phải chất lượng truy xuất |

### Trụ cột 3: Self-RAG & Kiểm chứng Grounding (Faithfulness & Relevance) (20.00/20 đã đo)

| Tiêu chí | Tối đa | Đạt | N | CI 95% | Trạng thái | Chi tiết |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| 3.1 Chống ảo giác câu trả lời (Answer Grounding) | 8 | 8.00 | 13 | – | ✅ PASS | Phát hiện ảo giác (recall) 7/7; không chặn nhầm câu sạch 6/6; điểm = trung bình hai tỷ lệ. Lưu ý: chỉ kiểm ID, giá, diện tích — không kiểm tiện ích/khoảng cách/nhận định định tính |
| 3.2 Context grounding & đề xuất ngân sách | 4 | 4.00 | 3 | – | ✅ PASS | ✔ Context hợp lệ được giữ nguyên | ✔ Ngân sách 2tr (sàn thị trường 3.5tr) → báo market gap, gợi ý KTX, đề xuất > 2tr | ✔ Đối chứng: ngân sách 5tr KHÔNG bị báo market gap |
| 3.3 Tính toàn vẹn Trace Events | 4 | 4.00 | 1 | – | ✅ PASS | ✔ Trace thật hợp lệ (id duy nhất, có type/node|tool, timestamp không lùi) — 6 sự kiện |
| 3.4 Độ phù hợp & Khớp câu hỏi (Answer Relevance Judge) | 4 | 4.00 | 8 | – | ✅ PASS | Đánh giá Answer Relevance (Rule-based Intent Coverage): Phát hiện trả lời lạc đề/bỏ sót câu hỏi 4/4; xác nhận câu trả lời đúng trọng tâm 4/4. |

### Trụ cột 4: Hỗ trợ Ra Quyết định & Cố vấn (Decision Support) (15.00/15 đã đo)

| Tiêu chí | Tối đa | Đạt | N | CI 95% | Trạng thái | Chi tiết |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| 4.1 Giải thích Top 1 trung thực | 5 | 5.00 | 3 | – | ✅ PASS | ✔ Có top_1_reason và key_factors | ✔ Lý do nêu ít nhất một yếu tố thực sự của Top 1 (giá/an ninh) | ✔ Không nhắc yếu tố chỉ thuộc Top 2 (tiện nghi/vị trí) |
| 4.2 Phân tích đánh đổi Top 1 vs Top 2 | 5 | 5.00 | 3 | – | ✅ PASS | ✔ Hướng so sánh nhất quán (rẻ↔nhỏ hoặc đắt↔rộng), không mâu thuẫn | ✔ Đảo chiều (Top 2 vs Top 1) cho kết quả đối xứng | ✔ Nêu đúng độ lệch: 500k và 6m² |
| 4.3 Độ trung thực khi render lời khuyên (Advice) | 5 | 5.00 | 3 | – | ✅ PASS | ✔ Giữ nguyên mọi nội dung đầu vào (intro, lý do, so sánh, checklist) | ✔ Không bịa số tiền ngoài dữ liệu đầu vào | ✔ Trường hợp 0 phòng: không lỗi, vẫn có intro/checklist, không hiện 'Top pick' — Đo template render lời khuyên; chất lượng nội dung do LLM sinh cần chấm bằng người/LLM-judge |

### Trụ cột 5: An toàn Hệ thống & Hiệu năng Vận hành (Safety & Efficiency) (15.00/15 đã đo)

| Tiêu chí | Tối đa | Đạt | N | CI 95% | Trạng thái | Chi tiết |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| 5.1 Guardrail chống tấn công (có đo chặn nhầm) | 6 | 6.00 | 23 | – | ✅ PASS | Chặn 16/16 tấn công (en 4/4, vi 4/4, zwsp 2/2, homoglyph 1/1, no_accent 1/1, case 1/1, malicious 3/3); cho qua đúng 7/7 câu hợp lệ |
| 5.2 Quét injection trong tin đăng bên thứ ba | 3 | 3.00 | 6 | 61–100% | ✅ PASS | Đúng 6/6 ca |
| 5.3 Độ trễ xử lý nội tại (không gồm LLM/IO) | 3 | 3.00 | 200 | – | ✅ PASS | p50 0.213 ms, p95 0.636 ms, max 1.655 ms (200 lần, sau 20 lần warm-up); ngân sách p95 ≤ 10 ms. Gồm chuỗi: Guardrails + apply_patch + MCDM weights + verify_context_grounding + build_decision_insights + verify_answer_grounding |
| 5.4 Nén payload & bảo toàn thông tin | 3 | 3.00 | 3 | – | ✅ PASS | ✔ Giảm ≥ 60% payload phình to | ✔ Giữ id/tiêu đề/giá/mô tả trong payload phình to | ✔ Không làm hỏng payload vốn đã gọn (giữ id/tiêu đề/giá/mô tả) — giảm 89.5% trên payload tổng hợp (số liệu này phụ thuộc payload mẫu, không phải trung bình thực tế) |

## 3. Giới hạn của phép đo

1. Bộ ca kiểm thử do chính nhóm phát triển viết, nên điểm số phản ánh mức tuân thủ các hành vi đã dự kiến, chưa phải khả năng tổng quát hoá. Nên bổ sung tập kiểm thử giữ riêng (held-out) lấy từ log thật, có người gán nhãn độc lập.
2. Số ca mỗi tiêu chí nhỏ; hãy đọc cột khoảng tin cậy 95% (Wilson) thay vì chỉ nhìn phần trăm.
3. Đây là kiểm thử mức thành phần. Chất lượng truy xuất (Precision@k/Recall/nDCG), độ đúng của câu trả lời do LLM sinh và độ trễ end-to-end được đo ở run_comprehensive_real_data_eval.py.
4. Khi model=None, hệ thống đánh giá các mô-đun xác định (State Patching, MCDM Weights, Hard Constraints, Grounding, Guardrails) và đánh dấu SKIP trung thực đối với tiêu chí phân loại ý định NLU cần LLM.