# 🤖 LangGraph Agent & An Toàn Chống Ảo Giác (AI Agent Graph Module)

Tài liệu này đặc tả chi tiết kiến trúc của phân hệ **AI Agent State Machine & Safety Guard** (`ai-agent/`).

---

## 1. LangGraph State Machine 8 Nodes

Đồ thị trạng thái hữu hạn điều phối luồng tư vấn và tìm kiếm:

```mermaid
flowchart TD
    START --> guardrail_node["1. guardrail_node<br/>Kiểm tra an toàn / prompt injection"]
    guardrail_node --> understand_node["2. understand_node<br/>Phân tích ý định & bóc tách tiêu chí"]
    
    understand_node -->|Thiếu thông tin cốt lõi / đa nghĩa| clarification_node["3. clarification_node<br/>Hỏi làm rõ yêu cầu"]
    understand_node -->|Câu hỏi chung / tư vấn cẩm nang| advisory_node["4. advisory_node<br/>Tư vấn pháp lý, thị trường, cẩm nang"]
    understand_node -->|Đủ điều kiện tìm phòng| retrieval_node["5. retrieval_node<br/>Truy vấn Hybrid Search Backend"]
    understand_node -->|Hỏi đáp phòng đã tìm| decision_node["6. decision_node<br/>Tổng hợp giải pháp & chọn top phòng"]
    
    retrieval_node --> decision_node
    
    decision_node --> verify_node["7. verify_node (Self-RAG)<br/>Kiểm chứng thông tin đối chiếu với DB"]
    verify_node -->|Grounding fail (retry <= 2)| decision_node
    verify_node -->|Grounding pass / fallback| formatter_node["8. formatter_node<br/>Định dạng Markdown / UI components"]
    
    clarification_node --> formatter_node
    advisory_node --> formatter_node
    
    formatter_node --> END
```

### Nguyên Tắc Phân Vùng Công Cụ (Tool Partitioning):
* `retrieval_node`: Chỉ được cấp `RETRIEVAL_TOOLS` (`search_listings_hybrid`, `get_nearby_locations`).
* `decision_node`: Chỉ được cấp `DETAIL_TOOLS` (`get_listing_detail`).
* `advisory_node`: Chỉ được cấp `ADVISORY_TOOLS` (`get_market_price_stats`).
* `formatter_node` / `response_node`: Không có quyền gọi tools, triệt tiêu ảo giác tool calls.

---

## 2. Các Cơ Chế Tối Ưu Hóa Trải Nghiệm (UX & Resilience)

1. **Proactive Search & Disambiguation Gate:**
   - Tự động bỏ qua hỏi lại khi truy vấn đã chứa trường ĐH hoặc quận cụ thể (ví dụ: *"Bách Khoa CS1 Q10"*).
   - Chỉ hỏi lại khi địa danh thực sự đa nghĩa (ví dụ: *"ĐH Bách Khoa"* không rõ Hà Nội hay TP.HCM).
2. **Adaptive Radius Retrieval (Bán kính thích ứng 2 pha):**
   - Khởi đầu với $R = 2.5$ km. Nếu số phòng hợp lệ < 3 và người dùng không cố định bán kính, tự động nới lỏng sang $3.5$ km $\rightarrow$ $5.0$ km.
3. **Từ Điển POI Trường Đại Học 0 ms (Local Campus Dictionary):**
   - Duy trì toạ độ chuẩn của các trường ĐH lớn tại TP.HCM/Hà Nội trong `university_campuses.json`, giải mã tức thì không tốn quota Geocoding.
4. **Dual-Mode LLM Compatibility:**
   - Tương thích song song cả LM Studio cục bộ (bảo toàn payload `thinking`) và Google Gemini / OpenAI Cloud (xóa `thinking` tránh lỗi 400).
5. **Rate Limit Resilience:**
   - Phân biệt Fast-fail cạn Quota ngày (`RESOURCE_EXHAUSTED` / 500 RPD) vs Exponential Backoff cho Rate Limit phút (15 RPM).

---

## 3. Cơ Chế Chống Ảo Giác Hai Tầng (Anti-Hallucination)

1. **Tầng 2A - Lọc Ràng Buộc Cứng Bằng Mã Lệnh (`check_hard_constraints`):**
   - 100% bằng code Python thuần (ngân sách $\pm 2\%$, diện tích, khoảng cách Haversine mặt cầu, tập loại phòng `allowed_room_types`, tiện ích bắt buộc).
   - Loại bỏ phòng vi phạm ngay lập tức kèm ghi nhận lý do cụ thể.
2. **Tầng 2B - Self-RAG Grounding (`verify_node`):**
   - Đối chiếu phát biểu của câu trả lời với dữ liệu thực tế từ Database.
   - Nếu phát hiện AI bịa tiện ích $\rightarrow$ Yêu cầu `decision_node` sinh lại (tối đa 2 lần retry).

