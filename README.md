# 🏠 Homigo — Smart Housing Decision Support System
### Hệ Thống Hỗ Trợ Ra Quyết Định Tìm Kiếm Phòng Trọ Thông Minh
> **Đồ Án Tốt Nghiệp** — Khoa Khoa học Máy tính / Kỹ thuật Phần mềm  
> Trường Đại học Công nghệ Thông tin — ĐHQG TP.HCM (**UIT - VNU-HCM**)

---

## 📌 1. Giới Thiệu Tổng Quan

**Homigo** là nền tảng tìm kiếm và hỗ trợ ra quyết định thuê phòng trọ thông minh dành cho sinh viên và người đi làm. Khác với các website đăng tin truyền thống chỉ lọc theo từ khóa cứng nhắc, Homigo tích hợp:
1. **Tìm kiếm lai (Hybrid Search)**: Kết hợp biểu diễn ngữ nghĩa dày đặc (**Dense pgvector Embedding**) và tìm kiếm từ khóa thưa thớt (**Sparse PostgreSQL Full-Text Search**) với tỷ lệ $70\% : 30\%$.
2. **Trọng số thích ứng theo ý định (Intent-Aware Dynamic MCDM)**: Tự động phân tích câu nói người dùng để kích hoạt các hệ số nhân ưu tiên (giá rẻ, gần trường, an ninh cao, full tiện nghi) và chuẩn hoá vector trọng số theo $L_1$-norm.
3. **Máy trạng thái điều phối AI Agent (LangGraph State Machine)**: Quản lý quy trình 6 node từ phòng thủ an toàn, tích lũy nhu cầu đa lượt (Multi-turn Memory), hỏi làm rõ khi mơ hồ, truy vấn dữ liệu đến phân tích đối sánh đánh đổi (**Trade-off Analysis**) và lập checklist kiểm tra thực tế.
4. **Bảo mật đa tầng (Dual-layer Security)**:
   - **Tầng Backend**: Middleware phát hiện tấn công **SQL Injection** và **Rate Limiting** bảo vệ tài nguyên API.
   - **Tầng AI Agent**: Guardrails chặn **Prompt Injection**, **Jailbreak** và lọc câu hỏi ngoài luồng (Off-topic).

---

## 🏗️ 2. Kiến Trúc Toàn Hệ Thống

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js 14+)                          │
│   • Giao diện tìm kiếm AI (/tim-kiem-ai): Chat, Thẻ phòng, Bản đồ      │
│   • Framework: React 18, TypeScript, TailwindCSS, Leaflet Map          │
└───────────────────▲────────────────────────────────▲───────────────────┘
                    │ (Text stream + RoomItem[])     │ (Direct API calls)
┌───────────────────▼────────────────────────┐       │
│        AI AGENT MODULE (ai-agent/)         │       │
│   • LangGraph Workflow (graph.py)          │       │
│   • Intent-Aware MCDM (intent_weights.py)  │       │
│   • Memory & State (memory.py)             │       │
│   • Guardrails Defense (guardrails.py)     │       │
└───────────────────▲────────────────────────┘       │
                    │ HTTP REST (housing_tools.py)   │
┌───────────────────▼────────────────────────────────▼───────────────────┐
│                        BACKEND API (FastAPI)                           │
│   • Security: SQL Injection Protection & Rate Limiting Middleware      │
│   • Search Engine: Hybrid Search (70% Dense pgvector + 30% Sparse FTS) │
│   • Reranker: 5-Factor Dynamic Multi-Criteria Decision (utils.py)      │
│   • Location & Geocode: Nominatim OSM + Administrative Hierarchy       │
└───────────────────▲────────────────────────────────────────────────────┘
                    │ SQLAlchemy ORM + pgvector
┌───────────────────▼────────────────────────────────────────────────────┐
│                    DATABASE (PostgreSQL 15+ / pgvector)                │
│   • Listings (tin đăng, toạ độ, concept_scores, 768-dim embeddings)    │
│   • Locations (Tỉnh/Thành phố -> Quận/Huyện -> Phường/Xã)              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📂 3. Cấu Trúc Dự Án

```tree
.
├── backend/                       # Backend REST API (FastAPI)
│   ├── app/
│   │   ├── api/v1/controllers/    # API Controllers (listings, locations, geocode, health)
│   │   ├── core/                  # Cấu hình, Database Session, Security Middlewares
│   │   ├── models/                # SQLAlchemy ORM Models (Listing, Location, User)
│   │   ├── repositories/          # Tầng truy vấn DB (Hybrid Search, pgvector, FTS)
│   │   ├── schemas/               # Pydantic Request/Response DTOs
│   │   ├── services/              # Nghiệp vụ (ListingService, Geocoder, Embedding)
│   │   └── utils/                 # Rerank đa tiêu chí 5 trọng số (utils.py)
│   ├── scripts/                   # Scripts khởi tạo DB và import dữ liệu mẫu
│   ├── tests/                     # Unit tests bảo mật & API (test_security_middleware.py)
│   ├── run.py                     # Script khởi chạy backend đơn giản
│   └── requirements.txt           # Thư viện phụ thuộc backend
│
├── frontend/                      # Web Client (Next.js 14 App Router)
│   ├── src/
│   │   ├── app/                   # App Router Pages (/tim-kiem-ai, /phong-tro, ...)
│   │   ├── components/            # UI Components (Cards, ChatBox, Map, Navbar)
│   │   ├── hooks/                 # React Hooks (useAiChat.ts, useLocation.ts)
│   │   └── services/              # API Client gọi Backend
│   └── package.json
│
├── ai-agent/                      # Module AI Agent Quyết Định (LangGraph)
│   ├── tools/                     # Native LangChain Tools & Tool Scoping Registry
│   │   ├── housing_tools.py       # Tools (search_rooms, geocode, detail, skills)
│   │   └── registry.py            # Phân vùng công cụ (RETRIEVAL, DETAIL, ADVISORY)
│   ├── graph.py                   # Máy trạng thái LangGraph 7 node với Tool Partitioning
│   ├── skills_discovery.py        # Engine khám phá kỹ năng động (Dynamic Skill Discovery)
│   ├── intent_weights.py          # Engine nhận diện Intent Multipliers & Dynamic Weights
│   ├── memory.py                  # Bộ nhớ phiên & Tích lũy tiêu chí người dùng
│   ├── guardrails.py              # Lớp bảo vệ Prompt Injection & Off-topic
│   ├── service.py                 # HousingAgentService cung cấp giao diện thực thi
│   ├── schemas.py                 # Schemas chuẩn (RoomItem, DecisionInsight, AgentResponse)
│   ├── eval/                      # Bộ 30 benchmark test cases & RAG Triad Grounding
│   └── tests/                     # 18 unit tests AI Agent (100% Passed)
│
├── crawler/                       # Module Thu Thập Dữ Liệu Phòng Trọ
│   ├── spiders/                   # Spiders cào dữ liệu (Nhà Tốt, Phongtro123)
│   ├── staging_db.py              # SQLite Staging DB (Kiến trúc Two-Tier Storage)
│   ├── etl/                       # Pipeline ETL làm sạch & nạp dữ liệu (Incremental ETL)
│   └── tests/                     # Unit tests Staging DB & Pipeline (100% Passed)
│
├── AGENT.md                       # Tài liệu kỹ thuật chi tiết dành cho AI Agents
├── run_backend.bat                # Phím tắt 1-click khởi chạy Backend trên Windows
└── README.md                      # Tài liệu tổng quan toàn bộ dự án (File này)
```

---

## ⚡ 4. Tính Năng & Điểm Nổi Bật Kỹ Thuật

### 4.1 Hybrid Search (Tìm Kiếm Lai)
Kết hợp tuyến tính giữa điểm tương đồng góc Cosine trên vector nhúng 768 chiều (`keepitreal/vietnamese-sbert`) và chỉ mục tìm kiếm toàn văn (`tsvector`/`tsquery`):
$$\text{CandidateScore} = 0.70 \times \text{DenseScore} + 0.30 \times \text{SparseScore}$$

### 4.2 Intent-Aware Dynamic MCDM (Trọng Số Thích Ứng Theo Ý Định)
Khi người dùng chat, hệ thống tự động phát hiện các từ khóa nhấn mạnh để kích hoạt **Intent Multipliers ($m_i$)**:
* **Giá rẻ / Tiết kiệm**: $m_{price} = 2.0\times$
* **Gần trường / Đi bộ được**: $m_{loc} = 2.0\times$
* **An ninh / Nữ ở một mình**: $m_{safe} = 2.0\times$
* **Full nội thất / Tiện nghi**: $m_{amen} = 1.8\times$

Sau đó chuẩn hoá trọng số theo công thức $L_1$-norm:
$$w_i = \frac{w_{base, i} \cdot m_i}{\sum_{k \in \text{active}} (w_{base, k} \cdot m_k)}$$

*Quy tắc kích hoạt:* Tiêu chí `price`, `safety`, `semantic` luôn bắt buộc; tiêu chí `location` chỉ kích hoạt khi có toạ độ địa lý; tiêu chí `amenity` chỉ kích hoạt khi người dùng yêu cầu tiện nghi cụ thể.

### 4.3 Máy Trạng Thái LangGraph
```mermaid
flowchart LR
    A[Guardrail Node] -->|An toàn| B[Preference & Intent Node]
    A -->|Vi phạm| F[Formatter Node]
    B -->|Mơ hồ| C[Clarification Node]
    B -->|Đủ thông tin| D[Retrieval & Rerank Node]
    C --> F
    D --> E[Decision Support Node]
    E --> F
    F --> END([Hoàn tất])
```

### 4.4 Bảo Mật API & Chống Tấn Công
* **`SQLInjectionMiddleware`**: Quét toàn bộ query string và URL path để ngăn chặn các mẫu injection nguy hiểm (`UNION SELECT`, `' OR 1=1`, `DROP TABLE`, `;--`).
* **`RateLimitMiddleware`**: Áp dụng thuật toán Sliding Window giới hạn 120 requests/phút theo IP, chống DoS và càn quét dữ liệu tự động.
* **`Guardrails`**: Chặn đứng các kỹ thuật Jailbreak, trích xuất system prompt và các câu hỏi ngoài phạm vi nhà ở.

---

## 🚀 5. Hướng Dẫn Cài Đặt & Vận Hành

### 5.1 Yêu Cầu Môi Trường
* **Python**: 3.11+
* **Node.js**: 18+ & npm
* **PostgreSQL**: 15+ (đã cài đặt extension `pgvector`)

---

### 5.2 Khởi Chạy Backend (FastAPI)

1. **Di chuyển vào thư mục backend:**
   ```powershell
   cd backend
   ```

2. **Cài đặt thư viện phụ thuộc:**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Thiết lập file cấu hình `.env`:**
   Tạo file `backend/.env` (tham khảo `backend/.env.example`):
   ```env
   PROJECT_NAME="Smart Housing Decision Support System API"
   POSTGRES_SERVER=localhost
   POSTGRES_PORT=5432
   POSTGRES_USER=postgres
   POSTGRES_PASSWORD=your_password
   POSTGRES_DB=smart_housing_db
   CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
   RATE_LIMIT_PER_MINUTE=120
   ```

4. **Khởi chạy Server:**
   * **Cách 1 (Nhanh nhất - One click):** Nhấp đúp vào file `run_backend.bat` hoặc chạy:
     ```powershell
     .\run_backend.bat
     ```
   * **Cách 2 (Bằng Python runner):**
     ```powershell
     python backend/run.py
     ```
   * **Cách 3 (Bằng Uvicorn trực tiếp):**
     ```powershell
     cd backend
     python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
     ```

5. **Truy cập tài liệu API tương tác:**
   * **Swagger UI:** [http://localhost:8000/docs](http://localhost:8000/docs)
   * **ReDoc:** [http://localhost:8000/redoc](http://localhost:8000/redoc)
   * **Health Check:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

### 5.3 Khởi Chạy Frontend (Next.js)

1. **Di chuyển vào thư mục frontend:**
   ```powershell
   cd frontend
   npm install
   ```

2. **Cấu hình môi trường:**
   Tạo file `frontend/.env.local`:
   ```env
   NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
   ```

3. **Khởi chạy máy chủ phát triển:**
   ```powershell
   npm run dev
   ```
   Truy cập trình duyệt tại: [http://localhost:3000/tim-kiem-ai](http://localhost:3000/tim-kiem-ai)

---

### 5.4 Sử Dụng Module AI Agent

1. **Di chuyển vào thư mục `ai-agent/`:**
   ```powershell
   cd ai-agent
   pip install -r requirements.txt
   ```

2. **Chạy thử nghiệm Agent qua mã Python:**
   ```python
   from service import HousingAgentService

   service = HousingAgentService()
   response = service.run("Tìm phòng trọ gần trường UIT dưới 3 triệu, có gác lửng và an ninh nhé")

   print("Câu trả lời:", response.text_reply)
   print("Số lượng phòng gợi ý:", len(response.rooms))
   if response.insights:
       print("Lý do lựa chọn Top 1:", response.insights.top_1_reason)
       print("Đối sánh đánh đổi:", response.insights.trade_offs)
   ```

---

## 🧪 6. Kiểm Thử & Đánh Giá Chất Lượng

### 6.1 Chạy Toàn Bộ Unit Tests

* **Kiểm thử AI Agent (13 tests):**
  ```powershell
  ai-agent\.venv\Scripts\pytest.exe ai-agent/tests/test_housing_agent.py -v
  ```
  *Bao phủ: Tools, Schemas, Guardrails, Memory State, Intent Weights, Multi-turn Accumulation, LangGraph Workflow.*

* **Kiểm thử Backend Security (4 tests):**
  ```powershell
  .venv\Scripts\pytest.exe backend/tests/test_security_middleware.py -v
  ```
  *Bao phủ: SQL Injection Blocking, Rate Limiting, Whitelist Bypass.*

### 6.2 Đánh Giá Độc Lập RAG Triad Grounding
Chạy script đo lường chất lượng sinh nội dung dựa trên bộ ba tiêu chuẩn RAG:
```powershell
ai-agent\.venv\Scripts\python.exe ai-agent/eval/rag_grounding_eval.py --limit 10
```
* **Context Relevance**: Độ liên quan giữa câu hỏi người dùng và ngữ cảnh phòng trọ thu thập được.
* **Groundedness (Faithfulness)**: Mức độ trung thực của câu trả lời (không bịa đặt giá, tiện ích hoặc toạ độ).
* **Answer Relevance**: Mức độ đáp ứng đúng và đủ yêu cầu của người dùng.

---

## 👥 7. Thông Tin Đồ Án Tốt Nghiệp

* **Sinh viên thực hiện:** Khoá luận tốt nghiệp ngành Kỹ thuật Phần mềm / Khoa học Máy tính
* **Trường:** Trường Đại học Công nghệ Thông tin — ĐHQG TP.HCM (**UIT**)
* **Repository Git:** [https://github.com/undead04/intelligent-room-rental.git](https://github.com/undead04/intelligent-room-rental.git)
* **Tài liệu chi tiết dành cho Agent:** Xem thêm tại file [`AGENT.md`](AGENT.md).
