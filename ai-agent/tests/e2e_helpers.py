"""Dựng Deps giả để chạy TRỌN đồ thị langgraph (không mạng, không LLM thật)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable, Optional

from langchain_core.messages import AIMessage, ToolMessage

from intelligence.advice import Advice
from graph import Deps, build_housing_graph, run_turn
from graph.nodes.clarification import ClarifyReply
from intelligence.nlu import PreferencePatch, Priorities, TurnAnalysis
from core.session_store import SessionStore
from tests.test_location_service import FakeDB

GOOD_ADVICE = Advice(intro="Mình tìm được vài phòng hợp với bạn nè.", top_reason="Gần điểm bạn muốn và giá dễ chịu.",
                     comparison="Top 1 thoáng hơn.", checklist=["Hỏi chủ nhà về giờ giấc"])
SKILL = SimpleNamespace(slug="rental-contract-advisor", name="Rental Contract Advisor", description="Tư vấn hợp đồng thuê trọ",
                        follow_ups=["Mẫu biên bản bàn giao phòng"], triggers=["hợp đồng"])


class _Bound:
    def __init__(self, llm: "FakeLLM", schema: type):
        self.llm, self.schema = llm, schema

    def invoke(self, messages: Any) -> Any:
        return self.llm._next(self.schema.__name__, messages)


class FakeLLM:
    """on(Schema, r1, r2, ...): lần gọi thứ i trả r_i (cái cuối lặp lại). r có thể là instance, Exception hoặc callable(messages)."""

    def __init__(self):
        self.queues: dict[str, list[Any]] = {}
        self.calls: list[tuple[str, Any]] = []

    def on(self, schema: Any, *results: Any) -> "FakeLLM":
        self.queues[schema if isinstance(schema, str) else schema.__name__] = list(results)
        return self

    def _next(self, name: str, messages: Any) -> Any:
        self.calls.append((name, messages))
        q = self.queues.get(name)
        if not q:
            raise RuntimeError(f"FakeLLM: chưa cấu hình {name}")
        r = q.pop(0) if len(q) > 1 else q[0]
        r = r(messages) if callable(r) else r
        if isinstance(r, Exception):
            raise r
        return r

    def with_structured_output(self, schema: type, **kw: Any) -> _Bound:
        return _Bound(self, schema)

    def invoke(self, messages: Any) -> Any:
        return SimpleNamespace(content=self._next("text", messages))

    def count(self, name: str) -> int:
        return sum(1 for n, _ in self.calls if n == name)


class FakeAgent:
    def __init__(self, *replies: list[Any]):
        self.replies, self.inputs = list(replies), []

    def invoke(self, payload: dict, config: Optional[dict] = None) -> dict:
        self.inputs.append(payload)
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return {"messages": payload["messages"] + r}


def agent_reply(text: str, tool: Optional[str] = None) -> list[Any]:
    out: list[Any] = [ToolMessage(content=tool, tool_call_id="t1")] if tool else []
    return out + [AIMessage(content=text)]


def raw_room(i: int, price: float = 2_400_000, area: float = 25.0, room_type: Any = None, title: Optional[str] = None, score: float = 0.9 - 0.05) -> dict:
    return {"listing": {"id": f"nhatot_{i}", "title": title or f"Phòng số {i}", "price_vnd": price, "area_m2": area, "address_raw": f"{i} Đường X, Dĩ An",
                        "lat": 10.871, "lng": 106.801, "main_image": "http://img", "images": ["a", "b"], "room_type": room_type},
            "match_score": score - i * 0.01, "explain_match": {"top_factors": [{"name": "price"}, {"name": "location"}]}}


def nlu(intent: str = "new_search", priorities: Optional[Priorities] = None, semantic_query: Optional[str] = None, **patch: Any) -> TurnAnalysis:
    return TurnAnalysis(intent=intent, patch=PreferencePatch(**patch), priorities=priorities or Priorities(), semantic_query=semantic_query)


class Harness:
    def __init__(self, llm: Optional[FakeLLM], rooms: Optional[list[dict]] = None, agent: Optional[FakeAgent] = None, geocode_ok: bool = True,
                 market: Optional[Callable[..., Any]] = None, critic: bool = False, **flags: Any):
        self.llm = llm
        self.rooms = rooms if rooms is not None else []
        self.search_calls: list[dict] = []
        self.skill_calls: list[tuple[str, str]] = []
        self.geo_calls: list[tuple] = []
        self.sessions = SessionStore()
        self.agent = agent
        db = FakeDB()

        def search(args: dict) -> dict:
            self.search_calls.append(args)
            rows = self.rooms(args) if callable(self.rooms) else self.rooms
            return {"ok": True, "data": rows}

        def geocode(q: str, hint: Optional[str]):
            self.geo_calls.append((q, hint))
            return {"lat": 10.87, "lng": 106.8} if geocode_ok else None

        def consult(slug: str, query: str) -> dict:
            self.skill_calls.append((slug, query))
            return {"ok": True, "instructions": "Hướng dẫn chi tiết về hợp đồng thuê trọ. " * 5, "references": {}}

        self.deps = Deps(
            sessions=self.sessions, get_llm=lambda role: self.llm, base_prompt="BASE", decision_system_prompt="DECISION",
            search_rooms=search, geocode=geocode, admin_lookup=db, consult_skill=consult, skills=lambda: {SKILL.slug: SKILL},
            market_fetcher=market, decision_agent=(lambda: self.agent) if agent else None, enable_critic=critic,
        )
        for k, v in flags.items():
            setattr(self.deps, k, v)
        self.graph = build_housing_graph(self.deps)

    def turn(self, text: str, session_id: Optional[str] = "s1", ui_action: Optional[str] = None):
        return run_turn(self.graph, text, session_id=session_id, ui_action=ui_action)

    @property
    def session(self):
        return self.sessions.get_or_create_session("s1")
