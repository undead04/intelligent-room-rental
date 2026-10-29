# 🧭 CẨM NANG ĐỌC HIỂU, CHỈNH SỬA & TINH CHỈNH SOURCE CODE (HOMIGO)

Tài liệu này được biên soạn dành cho bạn nhằm cung cấp lộ trình đọc mã nguồn thông minh nhất, giải thích mối liên kết giữa các thành phần và chỉ dẫn chính xác vị trí cần can thiệp khi muốn tinh chỉnh bất kỳ tính năng nào trong đồ án tốt nghiệp **Smart Housing Decision Support System (Homigo)**.

---

## 🗺️ 1. Bản Đồ Tổng Quan Hệ Thống (Architecture Big Picture)

Dự án gồm **4 phân hệ chính** tương hỗ chặt chẽ với nhau:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 14+)                          │
│   • Thư mục: frontend/                                                 │
│   • Trang trọng tâm: /tim-kiem-ai (3 Cột: Chat, Card Phòng, Bản Đồ)    │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │ (SSE Stream / JSON Response)   │ (REST API trực tiếp)
┌───────────────────▼────────────────────────┐       │
│        AI AGENT MODULE (ai-agent/)         │       │
│   • Máy trạng thái LangGraph 8 Node        │       │
│   • Intent-Aware Dynamic MCDM Weights      │       │
│   • Trí tuệ NLU & Self-RAG Grounding       │       │
│   • Cố vấn phân tích Đánh đổi (Trade-off)  │       │
└───────────────────▲────────────────────────┘       │
                    │ HTTP REST (housing_tools.py)   │
┌───────────────────▼────────────────────────────────▼───────────────────┐
│                        BACKEND (FastAPI)                               │
│   • Thư mục: backend/                                                  │
│   • Hybrid Search: 70% Dense pgvector + 30% Sparse FTS                 │
│   • MCDM Reranker: Chấm điểm 5 tiêu chí (Price, Loc, Safety, Amenity..)│
│   • Geocoding & Tra cứu địa giới hành chính                            │
└───────────────────▲────────────────────────────────────────────────────┘
                    │ ETL & Đẩy dữ liệu vào PostgreSQL
┌───────────────────┴────────────────────────┐
│             CRAWLER & ETL (crawler/)       │
│   • Cào tin từ PhongTro123, NhaTot...      │
│   • Trích xuất đặc trưng & sinh Embeddings │
└────────────────────────────────────────────┘
```

---

## 📖 2. Lộ Trình Đọc Code Khuyên Dùng (Reading Roadmap)

Để không bị "ngợp", bạn nên đọc theo **5 bước tuần tự** từ dữ liệu cốt lõi $\rightarrow$ thuật toán lõi $\rightarrow$ bộ não AI $\rightarrow$ giao diện:

### 🔹 Bước 1: Đọc Hợp Đồng Dữ Liệu (Domain Models & Schemas)
*Mục tiêu: Biết hệ thống đang quản lý những thông tin gì, cấu trúc dữ liệu gửi qua lại giữa các module.*
1. **`ai-agent/domain/schemas.py`**:
   - `UserPreferenceState`: Nhu cầu tích lũy của người dùng (ngân sách, tọa độ, tiện ích, ý định...).
   - `AgentResponse`: Cấu trúc JSON trả về cho Frontend (gồm `text_reply`, danh sách `rooms`, và `insights`).
   - `DecisionInsight`: Thông tin giải thích lý do chọn Top 1, bảng so sánh đánh đổi Trade-off với Top 2, và danh sách lưu ý kiểm tra khi đi xem phòng.
2. **`backend/app/schemas/listing.py`**:
   - `ListingVectorSearchBody`: Cấu trúc request tìm phòng gửi từ Agent sang Backend (query, coordinates, radius, dynamic weights).
3. **`frontend/src/app/tim-kiem-ai/types.ts`**:
   - Định nghĩa `RoomItem`, `AgentInsight`, `ChatMessage` bên giao diện React.

---

### 🔹 Bước 2: Đọc Trọng Tâm Thuật Toán Tìm Kiếm & Tái Xếp Hạng (Backend)
*Mục tiêu: Hiểu cách thức tìm ra Top 50 phòng và cách thuật toán MCDM chấm điểm từng căn.*
1. **`backend/app/repositories/listing_repository.py`** (Hàm `vector_search_candidates`):
   - Đọc cách kết hợp **Cosine Distance trên vector embedding** (70%) và **Full-Text Search tsvector** (30%) để lọc nhanh Top 50 ứng viên trong CSDL PostgreSQL pgvector.
2. **`backend/app/services/reranker.py`** (Hàm `rerank` & `explain_match`):
   - Đây là **trọng tâm thuật toán tốt nghiệp**! Xem cách tính điểm từng tiêu chí:
     - `price`: Điểm hợp lý giá từ mô hình định giá.
     - `location`: Khoảng cách Haversine (tính bằng km tới trường học/nơi làm).
     - `amenity`: Khớp danh sách tiện nghi yêu cầu (hỗ trợ cả từ khóa có dấu `"máy lạnh" -> "aircon"`).
     - `safety`: Điểm an ninh thực tế dựa trên tiện ích khóa vân tay, camera, bảo vệ.
     - `semantic`: Điểm tương đồng ngữ nghĩa.
   - Xem hàm `explain_match`: Trả về `top_factors` và `weak_factors` để AI giải thích cho người dùng.

---

### 🔹 Bước 3: Đọc "Bộ Não" Điều Phối Của AI Agent (`ai-agent/`)
*Mục tiêu: Hiểu quy trình từ lúc người dùng nhắn câu "tìm phòng gần UIT giá rẻ" đến khi ra kết quả.*
1. **`ai-agent/graph/state.py`**:
   - Xem cấu trúc `HousingAgentState` (State truyền qua các Node trong đồ thị LangGraph).
2. **`ai-agent/graph/builder.py`**:
   - Xem đồ thị luồng chạy qua 8 Node:
     - `guardrail_node` $\rightarrow$ `understand_node` $\rightarrow$ (`clarification_node` / `advisory_node` / `retrieval_node`) $\rightarrow$ `decision_node` $\rightarrow$ `verify_node` $\rightarrow$ `formatter_node`.
3. **`ai-agent/intelligence/intent_weights.py`**:
   - Xem cơ chế **Intent-Aware Dynamic MCDM**: Cách nhận diện người dùng đang nhấn mạnh yếu tố nào (ví dụ: "giá rẻ" $\rightarrow$ nhân 2.0x cho giá, "gần UIT" $\rightarrow$ nhân 2.0x cho vị trí) và chuẩn hóa $L_1$ ($\sum w_i = 1.0$).
4. **`ai-agent/graph/nodes/decision.py`**:
   - Node chuyên phân tích so sánh phòng: Lấy dữ liệu `explain_match` từ Backend, đối chiếu Top 1 vs Top 2, gọi LLM tạo lý do chọn lựa khách quan.
5. **`ai-agent/safety/grounding.py`** & **`graph/nodes/verify.py`**:
   - Cơ chế **Self-RAG Grounding**: Chống ảo giác (Anti-Hallucination). Kiểm tra xem mã phòng và giá tiền trong câu trả lời có khớp 100% với dữ liệu phòng thực tế hay không trước khi gửi cho khách.

---

### 🔹 Bước 4: Đọc Giao Diện Người Dùng (Frontend Next.js)
*Mục tiêu: Hiểu cách giao diện nhận dữ liệu, hiển thị 3 cột và cập nhật bản đồ thời gian thực.*
1. **`frontend/src/app/tim-kiem-ai/_hooks/useAiChat.ts`**:
   - Quản lý toàn bộ State của trang AI: gọi API `/chat/stream` dạng Server-Sent Events (SSE), cập nhật tin nhắn từng token, lưu danh sách phòng và insights.
2. **`frontend/src/app/tim-kiem-ai/page.tsx`**:
   - Bố cục 3 cột (Workspace 3 Columns):
     - Cột 1: `AiChatPanel.tsx` (Khung chat hội thoại).
     - Cột 2: `RoomResultsPanel.tsx` (Danh sách thẻ phòng + `AgentInsightPanel.tsx`).
     - Cột 3: `RoomMapPanel.tsx` (Bản đồ tương tác Leaflet ghim toạ độ các phòng).

---

### 🔹 Bước 5: Đọc Module Cào & Xử Lý Dữ Liệu (Crawler - Nếu quan tâm luồng dữ liệu thô)
1. **`crawler/spiders/`**: Spider cào dữ liệu từ các trang thuê trọ.
2. **`crawler/etl/`**: Làm sạch dữ liệu, sinh text mô tả chuẩn, gọi mô hình embedding sinh vector 768 chiều và nạp vào database.

---

## 🛠️ 3. Điểm "Vàng" Cần Biết Khi Sửa Đổi & Tinh Chỉnh (Customization Guide)

Dưới đây là các tình huống thực tế và chính xác những file bạn cần mở ra sửa:

### 🎯 Tình huống 1: Muốn sửa Từ khóa Nhận diện & Trọng số Ưu tiên (Intent MCDM)
* **File cần sửa:** [`ai-agent/intelligence/intent_weights.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/intelligence/intent_weights.py)
* **Những gì có thể chỉnh:**
  - `detect_intent_multipliers`: Thêm các từ khóa nhận diện mới vào các tuple `price_kws`, `loc_kws`, `safety_kws`, `amenity_kws`.
  - Thay đổi hệ số nhân (hiện tại `price: 2.0`, `location: 2.0`, `safety: 2.0`, `amenity: 1.8`).
  - Nếu muốn thêm hẳn một tiêu chí đánh giá thứ 6 (ví dụ: `area` - diện tích phòng), bạn cập nhật `CRITERIA` tại đây và cập nhật tương ứng ở `backend/app/services/reranker.py`.

---

### 🎯 Tình huống 2: Muốn đổi Giọng điệu (Tone of Voice) & Cách AI Đưa Ra Lời Khuyên
* **File cần sửa:**
  1. [`ai-agent/prompts/decision_prompt.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/prompts/decision_prompt.py)
  2. [`ai-agent/prompts/nlu_prompt.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/ai-agent/prompts/nlu_prompt.py)
* **Những gì có thể chỉnh:**
  - `ADVICE_RULES`: Hướng dẫn LLM xưng hô (ví dụ: "mình - bạn", "em - anh/chị", hoặc phong cách chuyên gia bất động sản).
  - Quy tắc định dạng câu trả lời: Nhấn mạnh vào an ninh, các mẹo đàm phán giá điện nước, hoặc bổ sung các lưu ý kiểm tra phòng trọ thực tế.

---

### 🎯 Tình huống 3: Muốn thêm một Kỹ năng Mới cho AI (Dynamic Skill Discovery)
Hệ thống hỗ trợ cơ chế mở rộng kỹ năng **không cần sửa code LangGraph**:
* **Thư mục:** Tạo thư mục mới tại `ai-agent/skills/<tên-kỹ-năng>/`
* **File tạo:** `ai-agent/skills/<tên-kỹ-năng>/SKILL.md`
* **Cấu trúc file mẫu:**
  ```markdown
  ---
  name: "tien-ich-xung-quanh-advisor"
  description: "Tư vấn về trạm xe bus, siêu thị, bệnh viện gần khu trọ"
  triggers:
    - "xe bus"
    - "trạm bus"
    - "siêu thị"
    - "chợ"
    - "tiện ích xung quanh"
  ---
  # Hướng dẫn nghiệp vụ
  Khi người dùng hỏi về xe bus đi lại tới UIT:
  1. Tuyến bus 19, 33, 52 đi qua Làng Đại học...
  ```
* Hệ thống trong `ai-agent/skills/skills_discovery.py` sẽ tự động quét file này và kích hoạt `advisory_node` khi người dùng hỏi trúng các từ khóa `triggers` mà không cần sửa 1 dòng code logic nào!

---

### 🎯 Tình huống 4: Muốn tinh chỉnh Thuật toán Search & Reranker Backend
* **File cần sửa 1:** [`backend/app/repositories/listing_repository.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/backend/app/repositories/listing_repository.py)
  - Thay đổi tỷ lệ kết hợp Hybrid Search (hiện tại: $0.70 \times \text{Dense} + 0.30 \times \text{Sparse}$).
  - Thay đổi số lượng ứng viên vòng 1 (`limit = 50`).
* **File cần sửa 2:** [`backend/app/services/reranker.py`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/backend/app/services/reranker.py)
  - Thay đổi ngưỡng khoảng cách địa lý (hiện tại $\le 1\text{km} \rightarrow 1.0$, giảm tuyến tính đến $10\text{km} \rightarrow 0.0$).
  - Bổ sung hoặc thay đổi bảng ánh xạ từ đồng nghĩa tiện ích (`ALIAS_MAPPING` như `"máy giặt" -> "washing_machine"`).

---

### 🎯 Tình huống 5: Muốn sửa Giao diện Tìm kiếm AI (Next.js Frontend)
* **File cần sửa:**
  - Muốn chỉnh khung chat hoặc bubble tin nhắn: [`frontend/src/app/tim-kiem-ai/_components/AiChatPanel.tsx`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/frontend/src/app/tim-kiem-ai/_components/AiChatPanel.tsx) & [`ChatMessageItem.tsx`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/frontend/src/app/tim-kiem-ai/_components/ChatMessageItem.tsx).
  - Muốn chỉnh giao diện thẻ phòng (Card): [`frontend/src/app/tim-kiem-ai/_components/RoomResultCard.tsx`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/frontend/src/app/tim-kiem-ai/_components/RoomResultCard.tsx) (thêm badge tiện ích, sửa hiển thị `matchScore`).
  - Muốn chỉnh bảng phân tích Trade-off: [`frontend/src/app/tim-kiem-ai/_components/AgentInsightPanel.tsx`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/frontend/src/app/tim-kiem-ai/_components/AgentInsightPanel.tsx).
  - Muốn chỉnh bản đồ: [`frontend/src/app/tim-kiem-ai/_components/RoomMapPanel.tsx`](file:///c:/UIT/Lab/Đồ%20Án%20tốt%20nghiệp/frontend/src/app/tim-kiem-ai/_components/RoomMapPanel.tsx).

---

## 🧪 4. Hướng Dẫn Chạy Test & Debug Khi Chỉnh Sửa

Khi bạn thực hiện bất kỳ sửa đổi nào, hãy dùng các lệnh sau để đảm bảo không bị lỗi hồi quy (regression bugs):

### 1. Chạy Unit Test của AI Agent
Môi trường ảo của AI Agent nằm tại `ai-agent/.venv`:
```powershell
# Chạy toàn bộ 30+ tests của ai-agent
ai-agent\.venv\Scripts\pytest.exe ai-agent/tests -v

# Chạy riêng test kiểm tra thuật toán trọng số động MCDM
ai-agent\.venv\Scripts\pytest.exe ai-agent/tests/test_intent_weights.py -v

# Chạy test kiểm tra NLU bóc tách tiêu chí
ai-agent\.venv\Scripts\pytest.exe ai-agent/tests/test_nlu.py -v
```

### 2. Chạy Unit Test Backend
```powershell
backend\.venv\Scripts\pytest.exe backend/tests -v
```

### 3. Chạy Đánh Giá RAG Triad & Chống Ảo Giác
```powershell
ai-agent\.venv\Scripts\python.exe ai-agent/eval/rag_grounding_eval.py --limit 5
```

### 4. Chạy Thử AI Agent Trực Tiếp Trong Script Python Nhanh
Nếu bạn vừa chỉnh sửa prompt hoặc trọng số và muốn xem câu trả lời thử mà không cần bật frontend:
```python
from service import HousingAgentService

service = HousingAgentService()
res = service.run("Tìm phòng trọ gần Đại học Công nghệ Thông tin dưới 3.5 triệu có máy lạnh và an ninh")

print("=== CÂU TRẢ LỜI ===")
print(res.text_reply)
print("\n=== SỐ PHÒNG TÌM ĐƯỢC ===", len(res.rooms))
if res.insights:
    print("\n=== LÝ DO CHỌN TOP 1 ===", res.insights.top_1_reason)
    print("\n=== PHÂN TÍCH ĐÁNH ĐỔI ===", res.insights.trade_off_analysis)
```

---

## 📌 5. Tóm Tắt Cheat Sheet Tra Cứu Nhanh

| Bạn muốn làm gì? | File chính cần mở | Ghi chú quan trọng |
| :--- | :--- | :--- |
| **Sửa công thức trọng số ưu tiên** | `ai-agent/intelligence/intent_weights.py` | Kiểm tra tổng trọng số luôn chuẩn hoá về 1.0 ($L_1$-norm) |
| **Sửa prompt tư vấn / tone giọng** | `ai-agent/prompts/decision_prompt.py` | Tuân thủ quy tắc không tự sinh số tiền giả để tránh ảo giác |
| **Thêm kỹ năng cẩm nang mới** | `ai-agent/skills/<tên>/SKILL.md` | Định nghĩa `triggers` trong YAML frontmatter |
| **Sửa tỷ lệ Hybrid Search (Dense/Sparse)** | `backend/app/repositories/listing_repository.py` | Đảm bảo hệ số nhân cộng lại bằng 1.0 (0.7 + 0.3) |
| **Sửa cách tính điểm tiện ích/vị trí** | `backend/app/services/reranker.py` | Xem các hàm `_haversine_km` và `_amenity_score` |
| **Sửa giao diện danh sách phòng & chat** | `frontend/src/app/tim-kiem-ai/` | Dùng hook `useAiChat.ts` để lấy dữ liệu |
| **Thêm bộ lọc tiện ích mới** | `frontend/src/lib/constants/property.ts` & `backend/app/services/reranker.py` | Khai báo đồng bộ cả frontend và backend |
