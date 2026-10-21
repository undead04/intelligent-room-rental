# 🎓 BÁO CÁO ĐÁNH GIÁ ĐỊNH LƯỢNG HỆ THỐNG AI AGENT (HOMIGO)
### Đề tài: Hệ thống hỗ trợ ra quyết định tìm kiếm phòng trọ thông minh
**Đơn vị:** Trường Đại học Công nghệ Thông tin (UIT - ĐHQG TP.HCM)
**Thời gian đánh giá:** 2026-10-25 21:40:21

---

## 🏆 1. TỔNG KẾT ĐIỂM SỐ HỘI ĐỒNG

- **Tổng điểm đạt được:** **`98.13 / 100.0`** Điểm
- **Xếp loại đồ án:** **`XUẤT SẮC (EXCELLENT)`**
- **Nhận định chung:** Hệ thống đạt tổng điểm 98.13/100 - Xếp loại: XUẤT SẮC (EXCELLENT). Mô hình hoàn thành xuất sắc các mục tiêu nghiên cứu của Đề tài tốt nghiệp: Tìm kiếm lai kết hợp Rerank đa tiêu chí động (Dynamic MCDM), máy trạng thái LangGraph 7 node phân vùng công cụ, kiểm chứng trung thực Self-RAG và cố vấn quyết định thông minh.

### 📊 Bảng điểm Tổng hợp 5 Trụ cột:

| STT | Trụ cột Đánh giá | Trọng số | Điểm đạt được | Tỷ lệ Đạt | Đánh giá |
| :---: | :--- | :---: | :---: | :---: | :---: |
| 1 | NLU & Trạng thái Tích lũy (State Tracking) | 25.0 | **23.33** | 93.3% | 🟢 Đạt |
| 2 | Dynamic MCDM & Độ liên quan Truy xuất (Retrieval) | 25.0 | **25.00** | 100.0% | 🟢 Đạt |
| 3 | Self-RAG & Kiểm chứng Grounding (Faithfulness) | 20.0 | **19.80** | 99.0% | 🟢 Đạt |
| 4 | Hỗ trợ Ra Quyết định & Cố vấn (Decision Support) | 15.0 | **15.00** | 100.0% | 🟢 Đạt |
| 5 | An toàn Hệ thống & Hiệu năng Vận hành (Safety & Efficiency) | 15.0 | **15.00** | 100.0% | 🟢 Đạt |
| | **TỔNG CỘNG** | **100.0** | **`98.13`** | **`98.1%`** | **`XUẤT SẮC (EXCELLENT)`** |

---

## 🔍 2. CHI TIẾT ĐÁNH GIÁ THEO TỪNG TIÊU CHÍ (RUBRIC BREAKDOWN)

### Trụ cột 1: NLU & Trạng thái Tích lũy (State Tracking) (23.33/25.0 điểm)

| Tiêu chí thành phần | Điểm tối đa | Điểm đạt | Tỷ lệ | Trạng thái | Chi tiết kiểm chứng |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 1.1 Phân loại Ý định (Intent Classification) | 5.0 | 3.33 | 66.7% | ⚠️ WARN | Đạt 4/6 ca kiểm tra các ý định cốt lõi |
| 1.2 Trích xuất Tiêu chí (Entity Extraction) | 10.0 | 10.00 | 100.0% | ✅ PASS | Bóc tách giá tiền, khoảng ngân sách, địa điểm và tiện ích chuẩn hoá đạt 100.0% |
| 1.3 Tích lũy Trạng thái & Rollback Đa lượt | 10.0 | 10.00 | 100.0% | ✅ PASS | Tích lũy chính xác qua các lượt và rollback snapshot ban đầu qua preference_history |

### Trụ cột 2: Dynamic MCDM & Độ liên quan Truy xuất (Retrieval) (25.00/25.0 điểm)

| Tiêu chí thành phần | Điểm tối đa | Điểm đạt | Tỷ lệ | Trạng thái | Chi tiết kiểm chứng |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 2.1 Phân phối Trọng số Động (Intent-Aware Dynamic MCDM) | 10.0 | 10.00 | 100.0% | ✅ PASS | Chuẩn hoá L1 đạt tổng = 1.0000; Kích hoạt ưu tiên giá x2.0 và an ninh x2.0 chuẩn xác |
| 2.2 Tuân thủ Ràng buộc Cứng (Hard Constraints & Exclusions) | 10.0 | 10.00 | 100.0% | ✅ PASS | Loại bỏ 100% phòng vượt trần ngân sách (+20% tolerance) và phòng thuộc loại hình KTX/Sleepbox bị loại trừ |
| 2.3 Ranh giới Hành chính & Bán kính Không gian (Spatial Proximity) | 5.0 | 5.00 | 100.0% | ✅ PASS | Phân giải phân cấp hành chính (Tỉnh/Thành -> Quận/Huyện -> Phường/Xã) và geocoding bán kính <= 8km |

### Trụ cột 3: Self-RAG & Kiểm chứng Grounding (Faithfulness) (19.80/20.0 điểm)

| Tiêu chí thành phần | Điểm tối đa | Điểm đạt | Tỷ lệ | Trạng thái | Chi tiết kiểm chứng |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 3.1 Tính Trung thực & Chống Ảo giác (Groundedness Score) | 10.0 | 9.80 | 98.0% | ✅ PASS | Không bịa đặt số liệu phòng, giá thuê, địa chỉ hoặc tiền cọc; bám sát 100% dữ liệu backend trả về |
| 3.2 Kiểm chứng Ngữ cảnh Dữ liệu (Context Grounding Verification) | 5.0 | 5.00 | 100.0% | ✅ PASS | Bộ lọc context grounding tự động phát hiện vi phạm và kích hoạt đề xuất đàm phán |
| 3.3 Truy vết Bằng chứng & Trace Events (Evidence Attribution) | 5.0 | 5.00 | 100.0% | ✅ PASS | Ghi nhận đầy đủ trace events cho từng lời gọi tool: resolve_location, search_rooms, market_fetcher |

### Trụ cột 4: Hỗ trợ Ra Quyết định & Cố vấn (Decision Support) (15.00/15.0 điểm)

| Tiêu chí thành phần | Điểm tối đa | Điểm đạt | Tỷ lệ | Trạng thái | Chi tiết kiểm chứng |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 4.1 Lý do Lựa chọn Top 1 Minh bạch (Top-1 Justification) | 5.0 | 5.00 | 100.0% | ✅ PASS | Giải thích Top 1 dựa trên vector trọng số cá nhân hoá (explain_match) thay vì liệt kê cảm tính |
| 4.2 Phân tích Đánh đổi Đối kháng Top 1 vs Top 2 (Trade-off Analysis) | 5.0 | 5.00 | 100.0% | ✅ PASS | Chỉ rõ điểm được - mất (giá rẻ hơn vs diện tích nhỏ hơn, gần trường hơn vs ít tiện ích hơn) |
| 4.3 Cố vấn Đàm phán khi 0 Phòng (Zero-Result Conversational Advisory) | 5.0 | 5.00 | 100.0% | ✅ PASS | Cung cấp mặt bằng giá sàn/trung bình thực tế và gợi ý khu vực lân cận, không ép nút bấm HITL |

### Trụ cột 5: An toàn Hệ thống & Hiệu năng Vận hành (Safety & Efficiency) (15.00/15.0 điểm)

| Tiêu chí thành phần | Điểm tối đa | Điểm đạt | Tỷ lệ | Trạng thái | Chi tiết kiểm chứng |
| :--- | :---: | :---: | :---: | :---: | :--- |
| 5.1 Rào chắn Bảo mật Đa lớp (Guardrail Security) | 5.0 | 5.00 | 100.0% | ✅ PASS | Ngăn chặn 3/3 cuộc tấn công Prompt Injection / Unsafe roleplay với chi phí 0 token |
| 5.2 Kiểm soát Dữ liệu Tin đăng Bên thứ ba (Data Sanitization) | 5.0 | 5.00 | 100.0% | ✅ PASS | Phát hiện và loại bỏ 2/2 tin đăng nghi ngờ chứa mã độc/injection |
| 5.3 Tối ưu hoá Độ trễ & Tài nguyên (Efficiency & Dual-Role LLM) | 5.0 | 5.00 | 100.0% | ✅ PASS | Phân tách Fast LLM (Thinking OFF, temp 0.0) và Main LLM (Thinking ON, temp 0.3); Tool Partitioning giảm 65% token bloat |

---

## 💡 3. ĐIỂM NỔI BẬT ĐÃ ĐƯỢC CHỨNG MINH KHI BÁO CÁO HỘI ĐỒNG

1. **Giải quyết triệt để vấn đề Context Bloat & Tool Hallucination**:
   - Nhờ cơ chế **Phân vùng công cụ (Tool Partitioning)** trong LangGraph, mỗi node chỉ nhận đúng scope công cụ cần thiết, tiết kiệm hơn 65% token overhead so với kiến trúc agent dùng chung một monolithic toolset.
2. **Cá nhân hoá thông minh với Intent-Aware Dynamic MCDM**:
   - Tự động nhận diện ý định ưu tiên (giá rẻ, an ninh cho nữ, vị trí sát trường) để tăng hệ số nhân và chuẩn hoá L1, giúp kết quả Rerank phản ánh chính xác nguyện vọng thực tế của người thuê trọ.
3. **Kiểm chứng Trung thực Self-RAG không phụ thuộc Human-in-the-Loop nút bấm**:
   - Toàn bộ lời khuyên khi không tìm thấy phòng trọ (Zero-Result) được sinh hoàn toàn đàm thoại tự nhiên, minh bạch số liệu thị trường thực tế (giá sàn, giá trung bình) và gợi ý khu vực lân cận, loại bỏ hoàn toàn các nút bấm HITL gượng gạo.
4. **Kiến trúc Tách biệt Fast Role & Main Role (Thinking Control)**:
   - Fast LLM (NLU, bóc tách tiêu chí) tắt chế độ Thinking và set `temperature=0.0` để tối ưu tốc độ phản hồi cực nhanh.
   - Main LLM (Decision Support, Cố vấn đánh đổi) bật chế độ Thinking để phân tích logic đối kháng đa chiều sâu sắc.