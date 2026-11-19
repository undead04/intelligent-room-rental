# 🤖 AI Agent Module — Smart Housing Decision Support (`ai-agent/`)

Module **AI Agent (`ai-agent/`)** đóng vai trò là bộ não tư vấn và hỗ trợ ra quyết định của hệ thống **Homigo**. Được xây dựng trên nền tảng **LangGraph 8-Node State Machine**, kết hợp mô hình **Intent-Aware Dynamic MCDM (Ra quyết định đa tiêu chí thích ứng theo ý định)**, **Multi-Turn Preference Memory**, **Dynamic Skill Discovery** và **Guardrails Security**.

---

## 🏗️ 1. Kiến Trúc Máy Trạng Thái 8-Node (`graph/builder.py` & `safety/grounding.py`)

```mermaid
flowchart LR
    START["User Message"] --> N1["1. guardrail_node<br/>(0 Tools)"]
    N1 -->|Vi phạm| N8["8. formatter_node"]
    N1 -->|An toàn| N2["2. understand_node<br/>(NLU + Multi-Intent TurnPlan + Dynamic Weights)"]
    N2 -->|Tư vấn / Skill| N4["4. advisory_node<br/>(ADVISORY_TOOLS)"]
    N2 -->|Thiếu thông tin / Mơ hồ| N3["3. clarification_node<br/>(0 Tools)"]
    N2 -->|Phản hồi trực tiếp / Đổi trang| N8
    N2 -->|Hỏi tiếp về phòng cũ| N6["6. decision_node<br/>(DETAIL_TOOLS)"]
    N2 -->|Đủ tiêu chí tìm kiếm| N5["5. retrieval_node<br/>(RETRIEVAL_TOOLS)"]
    N5 --> N6
    N5 -->|ambiguous / not_found / search_error| N7
    N4 --> N7
    N6 --> N7["7. verify_node<br/>(3-Tier Grounding + DoD Verifier)"]
    N7 -->|Retry <= 2 hoặc pending followup| N6
    N7 -->|Retry <= 2 hoặc pending advisory| N4
    N7 -->|pending search| N5
    N7 -->|pending search cần làm rõ| N3
    N7 -->|Pass / Fallback / Stop| N8
    N3 --> N8
    N8 --> END["AgentResponse"]
```

### Điểm Nổi Bật Thiết Kế
1. **Self-RAG Grounding, DoD Verifier & Trace Cô Lập (`safety/` & `graph/tracing.py`)**:
   - **Tầng Retrieval (`retrieval_node` & `resolve_location_with_retry`)**: Lọc cứng bằng code kiểm tra ràng buộc ngân sách ($\pm 2\%$), diện tích, khoảng cách Haversine, loại phòng (`allowed_room_types` / `excluded_room_types`) và tiện ích bắt buộc (không tự ý nới lỏng tiêu chí lọc khi kết quả rỗng). Khi định vị địa danh gặp `unresolved_point` hoặc `admin_not_found`, hệ thống thử lại tối đa 2 lần (`RESOLVE_LOCATION_MAX_RETRIES = 2`), nếu vẫn lỗi sẽ Fail-Fast dừng trước `search_rooms` và dọn sạch `location_text` lỗi khỏi `session.preferences`. Khi kết quả rỗng hoặc bị lọc hết, `retrieval_node` tóm tắt tối đa 5 ứng viên bị loại vào `dropped_summary` và tra cứu thống kê giá khu vực vào `market_context`.
   - **Tầng Generation & Free-form Decision (`decision_node` & `verify_node`)**: Mặc định `HOMIGO_CONSTRAINED_GENERATION=false` (trong `default_deps()`), cho phép ReAct `decision_agent` (`DETAIL_TOOLS`) tự do soạn câu trả lời Markdown linh hoạt cho cả lượt tìm mới và lượt hỏi tiếp; ở nhánh `0` phòng, LLM nhận đầy đủ `UserPreferenceState`, bán kính quét (`radius_km`), `dropped_summary`, `market_context` và khu vực lân cận (`neighbor_bullets`) để tự phân tích nguyên nhân và gợi ý hướng điều chỉnh (ghi bằng chứng vào `tool_evidence`; giữ `reply_when_no_rooms` làm fallback xác định và `ZeroResultAdvice` khi bật chế độ constrained). Validation 3 tầng (`schema_format` $\rightarrow$ `business_rule` $\rightarrow$ `external_cross_check`) đối chiếu mọi mã phòng, khoảng cách và giá tiền; nếu phát hiện ảo giác sẽ quay lại `decision_node` hoặc `advisory_node` để tự sửa sai (tối đa 2 lần).
   - **DoD Verifier độc lập (`safety/dod_verifier.py`) & `TraceStore` (`graph/tracing.py`)**: Mọi model call, tool call (kèm `state_before`/`state_after`) và quyết định verifier được ghi nối tiếp dạng JSONL theo `run_id`/`seq` độc lập ngoài State; `verify_dod` kiểm chứng trên bản chụp bất biến và buộc thực thi hành vi thoát xác định (`retry`, `ask_user`, `fallback_template`, `stop_and_report`) khi `passed = False`.
2. **Multi-Intent Plan & Execute (`TurnPlan` & `graph/routing.py`)**:
   - Khi `understand_node` phát hiện nhiều mệnh đề độc lập (`followup`, `search`, `advisory`) trong cùng một câu, `TurnPlan` lập hàng đợi `pending_tasks` theo đúng thứ tự xuất hiện (`task_order`). Mỗi bước đều đi qua `verify_node` trước khi `_route_pending_task` lưu kết quả vào `partial_replies` và chuyển tiếp sang bước kế tiếp; cuối cùng `formatter_node` gộp thành một `AgentResponse` duy nhất.
3. **Tool Partitioning (`tools/registry.py`)**: Phân vùng công cụ chặt chẽ theo từng Node — `RETRIEVAL_TOOLS` (`search_rooms`), `DETAIL_TOOLS` (`get_listing_detail`), `ADVISORY_TOOLS` (`list_housing_skills`, `consult_housing_skill`, `get_market_price_stats`), giúp giảm token overhead và ngăn LLM gọi nhầm tool.
4. **NLU Toàn Quyền Cloud LLM (0 Regex Ngữ Nghĩa) & L1 Dynamic Weighting (`intelligence/nlu.py`, `intent_weights.py`)**:
   - Cloud LLM (`temperature = 0.0`, nâng `0.3` khi retry) xuất structured output `TurnAnalysis` (`patch.clear`, `excluded_room_types`, `task_order`, `page_action`, `revert_mode`, `is_location_pivot`, `Priorities`: `lower: 0.5x`, `normal: 1.0x`, `high: 2.0x`, `very_high: 3.0x` qua `LEVEL_TO_MULT`) kèm `priority_reasons`.
   - Tự động bật/tắt tiêu chí động (`location` chỉ bật khi có tọa độ/địa điểm; `amenity` chỉ bật khi có yêu cầu tiện nghi) và chuẩn hóa $L_1$-norm ($\sum w_i = 1.0$).
5. **Multi-Turn Memory, Phân Trang 10 Trang & Tra Cứu Rank Toàn Cục (`core/session_store.py`)**:
   - Tích lũy tiêu chí (`location_text`, `lat`, `lng`, `min_price`, `max_price`, `amenities`, `special_requirements`) xuyên suốt nhiều lượt hội thoại trong SQLite `sessions.db`, tự động reset tọa độ `lat`/`lng` khi chuyển khu vực mới.
   - Pre-fetch tối đa `MAX_PAGED_ROOMS = 50` phòng (`10` trang $\times$ `5` phòng/trang) vào `SessionData.paged_rooms`, hỗ trợ chuyển trang kép qua UI (`GET /api/v1/session/{session_id}/rooms`) hoặc qua chat (`_parse_page_navigation`) với `0` LLM/Vector Search, và tra cứu `room.rank` toàn cục khi hỏi tiếp ở bất kỳ trang nào.
6. **Dynamic Skill Discovery (`skills/skills_discovery.py`)**:
   - Tự động quét thư mục `ai-agent/skills/*/SKILL.md` (`rental-contract-advisor`, `market-price-advisor`), hỗ trợ tham vấn đơn hoặc đa kỹ năng (`skill_slugs` / `matched_skills`) qua `skill_context` cô lập (không ghi đè `session.preferences`), và có cơ chế `is_market_only_patch` ngăn việc coi nhầm truy vấn giá thị trường thành tác vụ `search`.
7. **Decision Insights & Trade-off Analysis (`intelligence/decision.py`)**:
   - Giải thích rõ vì sao phòng Top 1 đạt điểm cao nhất dựa trên `explain_match` từ Backend, phân tích đánh đổi (Trade-off) với Top 2 và sinh danh sách kiểm tra thực tế (`verification_checklist`).

---

## 📂 2. Cấu Trúc Thư Mục (Layered Architecture 6 Tầng)

```text
ai-agent/
├── api/                         # FastAPI Endpoints (/chat, /chat/stream SSE, /health, /session)
├── core/                        # Cấu hình Pydantic Settings, LLM Factory, Paths, SQLite SessionStore
├── domain/                      # Schemas chuẩn (AgentResponse, RoomItem, DecisionInsight), Enums, Budget
├── intelligence/                # NLU, Intent Multipliers & L1 Dynamic MCDM, Trade-offs, Insights & Advice
├── prompts/                     # System Prompts tách biệt (nlu_prompt.py, decision_prompt.py, advisory_prompt.py)
├── safety/                      # Guardrails, Self-RAG Grounding 3 tầng & DoD Verifier độc lập (dod_verifier.py)
├── graph/                       # LangGraph State Machine 8 Node & TraceStore JSONL (tracing.py)
│   ├── builder.py               # StateGraph construction & Conditional edges
│   ├── state.py                 # HousingAgentState TypedDict (kèm dropped_summary, market_context, verifier_result)
│   ├── routing.py               # Dynamic Routing logic
│   ├── tracing.py               # TraceStore JSONL cô lập theo run_id/seq + che PII
│   └── nodes/                   # guardrail, understand, clarification, advisory, retrieval, decision, verify, formatter
├── tools/                       # Native LangChain Tools & Phân vùng Scopes (RETRIEVAL, DETAIL, ADVISORY)
├── skills/                      # Dynamic Skill Discovery qua YAML triggers (rental-contract-advisor, market-price-advisor)
├── eval/                        # Bộ đánh giá (run.py, thesis_eval_rubric.py, stability_and_regression.py, answer_relevance.py, stats_analyzer.py)
├── eval_results/                # Báo cáo & JSON kết quả đánh giá (report.md, thesis_evaluation_report.md, ...)
├── utils/                       # Tiện ích text, geo & đóng băng bất biến (freeze.py)
├── tests/                       # 610 Unit & Integration Tests (100% Passed)
├── main.py                      # Uvicorn entrypoint (Port 8001)
└── pyproject.toml / uv.lock     # Quản lý phụ thuộc uv
```

---

## 🚀 3. Hướng Dẫn Cài Đặt & Sử Dụng

### 3.1. Cài Đặt Môi Trường
```powershell
cd ai-agent
uv sync
```
Hoặc sử dụng môi trường ảo có sẵn tại `ai-agent/.venv`. Thiết lập file `ai-agent/.env`:
```env
OPENAI_API_KEY=your_api_key
MODEL_NAME=gpt-4o-mini
SEARCH_ROOM_API_BASE=http://localhost:8000/api/v1
# Tùy chọn: đặt true để ép output theo JSON schema (Advice/ZeroResultAdvice), mặc định false để Agent viết phản hồi Markdown tự do
HOMIGO_CONSTRAINED_GENERATION=false
```

### 3.2. Gọi `HousingAgentService` Trong Python
```python
from api.routes import HousingAgentService

service = HousingAgentService()
res = service.run(
    user_message="Tìm phòng trọ gần ĐH CNTT (UIT) dưới 3 triệu có máy lạnh, gác lửng",
    session_id="user_session_01",
)

print(res.text_reply)
print("Số phòng phù hợp:", len(res.rooms))
if res.insights:
    print("Lý do chọn Top 1:", res.insights.top_1_reason)
```

---

## 🧪 4. Chạy Kiểm Thử & Đánh Giá (Unit Tests & Evaluation)

Chạy toàn bộ 610 unit & integration tests của Homigo AI Agent (100% Passed):
```powershell
.\ai-agent\.venv\Scripts\pytest.exe ai-agent/tests -q
```

Chạy các bộ đánh giá định lượng (Evaluation Suites):
```powershell
# 1. Chạy bộ đánh giá toàn diện (Guardrail 137 ca + Grounding 600 ca + Agent Eval pass^3 + Ablation E2E)
# Lưu ý: suite `ablation` gọi LLM + Backend API thực (bật Backend port 8000 trước; --pacing 4.5 cho Gemini Free Tier 15 RPM)
cd ai-agent; .\.venv\Scripts\python.exe -m eval.run guardrail grounding agent_eval ablation --pacing 4.5 --out eval_results

# (Hoặc chạy offline không cần Backend/LLM E2E):
.\.venv\Scripts\python.exe -m eval.run guardrail grounding agent_eval --out eval_results

# 2. Chạy thang điểm 5 trụ cột (offline deterministic; thêm --with-model để chấm NLU bằng LLM)
.\.venv\Scripts\python.exe -m eval.thesis_eval_rubric --with-model
```

Kết quả đo đạc mới nhất được xuất ra [`eval_results/report.md`](eval_results/report.md) và tổng hợp chung tại [`docs/evaluation/reports/2026-11-evaluation-summary.md`](../docs/evaluation/reports/2026-11-evaluation-summary.md):
- **Guardrail (137 ca):** Recall tấn công ngoài nhóm HARD `100.0% (83/83)` (`95.4%` cả nhóm HARD), chặn nhầm `0.0% (0/40)`.
- **Grounding (600 ca):** Phát hiện lỗi tiêm vào `100.0% (480/480)`, gắn cờ nhầm `0.0% (0/120)`.
- **NLU (40 ca vàng):** Khớp hoàn toàn cả ca `82.5% (33/40)`.
- **Ablation E2E:** Đạt `92.9% (39/42)` checks, `0.0% (0/7)` lỗi tới tay người dùng và `0.0% (0/7)` fallback câu mẫu.
- **Agent Eval (`2026.11.v3`, 18 ca, `k=3`):** Không bước cấm/thừa (Trajectory Q2) `100.0% (54/54)`, DoD Verifier `82.1% (32/39)`, `pass^3 = 38.9% (7/18)`.
