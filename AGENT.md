# 🤖 AGENT.MD — Hướng Dẫn Kiến Trúc & Ngữ Cảnh Dành Cho AI Agent

Tài liệu này được biên soạn để bất kỳ AI Agent hoặc lập trình viên nào khi bắt đầu phiên làm việc (new session) đều có thể nắm bắt ngay toàn bộ kiến trúc, trạng thái hiện tại và cách vận hành của hệ thống **Smart Housing Decision Support System (Homigo)**.

---

## 📌 1. Tổng Quan Dự Án
* **Tên đề tài:** Hệ thống hỗ trợ ra quyết định tìm kiếm phòng trọ thông minh (Smart Housing Decision Support System).
* **Đơn vị:** Đồ án tốt nghiệp — Trường Đại học Công nghệ Thông tin (UIT - ĐHQG TP.HCM).
* **Mục tiêu:** Hỗ trợ sinh viên và người thuê phòng tìm kiếm chỗ ở tối ưu bằng cách kết hợp:
  1. Tìm kiếm ngữ nghĩa (Semantic Vector Search)
  2. Xếp hạng đa tiêu chí (Multi-Criteria Reranking 5 trọng số)
  3. Cố vấn quyết định bằng AI Agent (Giải thích lý do lựa chọn & Phân tích đánh đổi trade-offs)

---

## 🏗️ 2. Kiến Trúc Toàn Hệ Thống

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 14+)                          │
│   • Trang tìm kiếm AI: /tim-kiem-ai (3 Cột: Chat, Card List, Map)       │
│   • Interface dữ liệu phòng: RoomItem (id, rank, matchScore, lat, lng) │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │ (Text stream + RoomItem[])     │ (Direct API calls)
┌───────────────────▼────────────────────────┐       │
│        AI AGENT MODULE (ai-agent/)         │       │
│   • Persona: Homigo Smart Housing Advisor  │       │
│   • Engine: LangChain Core + Native Tools  │       │
│   • Service: HousingAgentService           │       │
│   • Schemas: AgentResponse, DecisionInsight│       │
└───────────────────▲────────────────────────┘       │
                    │ HTTP REST (housing_tools.py)   │
┌───────────────────▼────────────────────────────────▼───────────────────┐
│                        BACKEND (FastAPI + SQLA)                        │
│   • GET  /api/v1/geocode: Chuyển tên địa điểm thành (lat, lng)         │
│   • GET  /api/v1/locations/*: Tra cứu cây Tỉnh/Thành -> Quận -> Phường │
│   • POST /api/v1/listings/vector-search:                               │
│       - Bước 1: Hybrid Search (70% Dense pgvector + 30% Sparse FTS)    │
│       - Bước 2: Rerank đa tiêu chí 5 trọng số (utils.py)               │
│       - Trả về: Listing + match_score + explain_match                  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🧠 3. Chi Tiết Module `ai-agent/`

### 3.1 Cấu trúc file cốt lõi
* **[`ai-agent/tools/housing_tools.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/tools/housing_tools.py)**: Native LangChain tools giao tiếp trực tiếp với FastAPI backend:
  * `geocode_location`: Tìm toạ độ `(lat, lng)` từ tên trường, toà nhà, đường.
  * `get_location_hierarchy`: Tra cứu ID thành phố, quận, phường.
  * `search_rooms`: Tìm phòng qua vector search + rerank của backend.
  * `get_listing_detail`: Lấy chi tiết bài đăng theo ID.
* **[`ai-agent/schemas.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/schemas.py)**: Pydantic schemas chuẩn hoá:
  * `RoomItem`: Định dạng chuẩn khớp 100% với Frontend `tim-kiem-ai/types.ts`.
  * `DecisionInsight`: Giải thích lý do chọn Top 1, bảng so sánh Trade-off với Top 2/Top 3, checklist lưu ý khi đi xem phòng.
  * `AgentResponse`: Cấu trúc JSON hoàn chỉnh trả về cho Client.
* **[`ai-agent/guardrails.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/guardrails.py)**: Lớp phòng thủ Security & Safety:
  * Phát hiện và chặn đứng Prompt Injection & Jailbreak attempts.
  * Lọc câu hỏi ngoài luồng (off-topic) không liên quan đến nhà ở / phòng trọ, phản hồi an toàn tức thì với 0 token cost.
* **[`ai-agent/memory.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/memory.py)**: Quản lý Bộ nhớ & Trạng thái tiêu chí (Memory & State Management):
  * Theo dõi và tích lũy trạng thái nhu cầu (`UserPreferenceState`: vị trí, ngân sách, tiện ích, yêu cầu mềm) xuyên suốt nhiều lượt chat.
  * Quản lý cửa sổ ngữ cảnh (Context Window Compaction): Tự động nén tin nhắn cũ và tiêm `[ACCUMULATED PREFERENCE STATE]` vào đầu ngữ cảnh để Agent không bao giờ bị quên tiêu chí cũ.
* **[`ai-agent/service.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/service.py)**: Lớp `HousingAgentService` điều phối toàn bộ:
  * Kiểm tra Guardrails trước khi gọi model.
  * Xây dựng ngữ cảnh từ `memory_manager`.
  * Chạy LangChain Agent, tự động trích xuất kết quả `search_rooms` từ tool message thành `RoomItem[]`.
  * Tạo `DecisionInsight` tự động dựa vào `explain_match`.
  * Lưu trữ lượt chat vào session memory và trả về `AgentResponse` kèm `current_preferences`.
* **[`ai-agent/prompts.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/prompts.py)**: System prompt chuyên nghiệp:
  * Persona: Homigo Smart Housing Decision Support Advisor.
  * Hướng dẫn Agent chủ động hỏi làm rõ (proactive clarification) khi yêu cầu quá mơ hồ.
  * Tuyệt đối không bịa đặt dữ liệu (hallucination-free).
* **[`ai-agent/agent.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/agent.py)**: Khởi tạo Agent với Native Tools và Middleware giới hạn an toàn.
* **[`ai-agent/eval/`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/eval/)**:
  * `dataset.json`: Bộ 30 test cases đa dạng nhóm phục vụ đánh giá định lượng.
  * `run_eval.py`: Script benchmark tự động đo Schema Validity, Task Completion, Hallucination-free, Latency và xuất file `eval_report.md`.
  * `rag_grounding_eval.py`: Script đo lường bộ ba tiêu chí **RAG Triad & Grounding** (Context Relevance, Groundedness/Faithfulness, Answer Relevance) và xuất báo cáo `rag_grounding_report.md`.

---

## ⚖️ 4. Cơ Chế Rerank Đa Tiêu Chí (`backend/app/utils/utils.py`)
Hệ thống backend sử dụng công thức tổng có trọng số động (MCDM Dynamic Weights) với 5 thành phần:

$$\text{FinalScore} = w_{price} S_{price} + w_{sem} S_{semantic} + w_{loc} S_{location} + w_{amen} S_{amenity} + w_{safe} S_{safety}$$

1. **`price` ($S_{price}$)**: Điểm giá phòng (`price_score`), dữ liệu được cập nhật từ crawler ETL.
2. **`semantic` ($S_{semantic}$)**: Điểm độ tương đồng Cosine giữa nhu cầu mô tả và embedding bài đăng.
3. **`location` ($S_{location}$)**: Tính khoảng cách Haversine từ toạ độ người dùng đến phòng, chuẩn hoá: $\le 1\text{km} \rightarrow 1.0$, $\ge 10\text{km} \rightarrow 0.0$.
4. **`amenity` ($S_{amenity}$)**: Tỷ lệ khớp các tiện ích yêu cầu (dựa trên `concept_scores` của tin đăng).
5. **`safety` ($S_{safety}$)**: Điểm an ninh khu vực (`safety_score` từ 0.0 đến 1.0).

Backend tự động sinh `explain_match` chứa `top_factors` và `weak_factors` để AI Agent diễn giải cho người dùng.

---

## 🚀 5. Hướng Dẫn Vận Hành & Lệnh Thường Dùng

### Môi trường ảo Python
* Backend: `.venv` tại thư mục gốc hoặc `backend/.venv`
* AI Agent: `ai-agent/.venv`

### Chạy Unit Test AI Agent:
```powershell
cd ai-agent
.\.venv\Scripts\pytest.exe tests/test_housing_agent.py
```

### Chạy Đánh Giá Benchmark:
```powershell
cd ai-agent
.\.venv\Scripts\python.exe eval/run_eval.py --limit 5
```

### Sử dụng Agent Service trong Python code:
```python
from service import HousingAgentService

service = HousingAgentService()
res = service.run("Tìm phòng trọ gần trường Đại học Công nghệ Thông tin UIT dưới 3 triệu")
print("Câu trả lời:", res.text_reply)
print("Số phòng tìm được:", len(res.rooms))
if res.insights:
    print("Top 1 ID:", res.insights.selected_top_1_id)
    print("Lý do chọn:", res.insights.top_1_reason)
```

---

## 📝 6. Hướng Dẫn Cho Các Session Tiếp Theo
1. **Frontend Integration**: Khi kết nối giao diện Next.js (`frontend/src/app/tim-kiem-ai`), chỉ cần trỏ API từ `useAiChat.ts` vào backend endpoint gọi `HousingAgentService.run()` và nạp danh sách `res.rooms` vào state `rooms` để render thẻ phòng và bản đồ.
2. **Crawler ETL**: Khi viết module crawler, chú ý tính toán và lưu thêm giá trị `price_score` (0.0 - 1.0) vào cột `price_score` trong bảng `listings` để tiêu chí giá trong Rerank đạt hiệu quả tối đa.
