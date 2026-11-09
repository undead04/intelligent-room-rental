# 0003: Phân Quyền Công Cụ & State Machine 8 Nodes (LangGraph)

- **Trạng thái:** Accepted
- **Ngày quyết định:** 2026-10-25
- **Phạm vi:** `ai-agent/core/builder.py`, `ai-agent/tools/registry.py`, `ai-agent/safety/`

---

## 1. Bối Cảnh (Context)
Các AI Chatbot dạng ReAct đơn giản thường gặp phải 2 lỗi nghiêm trọng:
1. **Ảo giác phòng trọ (Hallucination):** Tự bịa ra địa chỉ hoặc giá phòng không có thật trong cơ sở dữ liệu.
2. **Loạn tool calling:** LLM gọi bừa các công cụ nhạy cảm hoặc rơi vào vòng lặp vô tận khi truy vấn người dùng mơ hồ.

---

## 2. Quyết Định (Decision)
1. **Kiến trúc State Machine 8 Nodes:**
   Sử dụng LangGraph điều phối luồng tuần tự và có điều kiện rõ ràng:
   - `input_node` $\rightarrow$ `intent_node` $\rightarrow$ `preference_node` $\rightarrow$ `retrieval_node` $\rightarrow$ `rerank_node` $\rightarrow$ `verify_node` $\rightarrow$ `response_node` (hoặc rẽ nhánh sang `clarify_node`).
2. **Tool Partitioning (Phân quyền công cụ nghiêm ngặt):**
   - Chỉ các Node được chỉ định mới có quyền gọi Tools tương ứng.
   - LLM sinh câu trả lời cuối cùng (`response_node`) **không có quyền gọi tool tìm kiếm**, ngăn chặn triệt để tình trạng hallucinate tool calls.
3. **Cơ chế Self-RAG Grounding (`verify_node`):**
   - Tự động đối chiếu thông tin phòng trả về với dữ liệu thực tế từ Database.
   - Nếu vi phạm các ràng buộc cứng (giá tối đa, khoảng cách tối đa, loại phòng cấm), hệ thống tự động loại bỏ trước khi chuyển cho LLM tổng hợp lời khuyên.

---

## 3. Hệ Quả & Đánh Đổi (Consequences)
- **Tích cực:** Tỷ lệ ảo giác (Hallucination Rate) giảm xuống mức $\approx 0\%$, đảm bảo tính trung thực (Faithfulness) đạt trên 4.7/5.0 trong các bài đánh giá.
- **Đánh đổi:** Luồng xử lý có độ trễ lớn hơn ReAct một lượt đơn giản, cần tối ưu bằng streaming SSE và xử lý song song các tác vụ I/O.

