"""Tiêm phụ thuộc (Dependency Injection) cho đồ thị LangGraph.

Gom toàn bộ I/O, LLM, cấu hình và công cụ vào MỘT cấu trúc; các node chỉ nhận deps qua factory make_node(deps).
Giúp test được toàn bộ đồ thị bằng Fake/Stub mà không cần mock rải rác.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Optional

from core import MODEL_CALL_LIMIT, TOOL_CALL_LIMIT
from domain.budget import MarketFetcher
from graph.tracing import PROMPT_VERSION, SKILL_VERSION, TraceStore, get_active_trace_store, resolve_versions
from safety.grounding import MAX_GROUNDING_RETRIES
from safety.guardrails import GuardrailResult, check_guardrails
from tools.location_service import AdminLookup


@dataclass
class Deps:
    sessions: Any                                            # SessionStore: get_or_create_session / commit_turn
    get_llm: Callable[[str], Any]                            # "main" | "fast" -> chat model | None
    base_prompt: str
    decision_system_prompt: str
    search_rooms: Callable[[dict[str, Any]], dict[str, Any]]            # args -> {"ok": bool, "data": [...], "error"?}
    geocode: Callable[[str, Optional[str]], Optional[dict[str, float]]]
    admin_lookup: AdminLookup
    consult_skill: Callable[[str, str], dict[str, Any]]                 # (slug, query) -> {"ok", "instructions", "references"}
    skills: Callable[[], dict[str, Any]]                                # slug -> SkillMetadata
    advice_system_prompt: str = ""
    market_fetcher: Optional[MarketFetcher] = None
    decision_agent: Optional[Callable[[], Any]] = None                  # factory -> agent.invoke({"messages": [...]}, config=...)
    guard: Callable[[str], GuardrailResult] = check_guardrails
    enable_critic: bool = False
    trace_store: Optional[TraceStore] = None
    prompt_version: str = PROMPT_VERSION
    skill_version: str = SKILL_VERSION
    model_version: str = ""
    # --- công tắc cho ablation (mặc định = cấu hình đầy đủ) ---
    constrained_generation: bool = True           # False: kết quả mới cũng do agent viết tự do
    verify_answers: bool = True                   # False: vẫn ĐO lỗi (issues) nhưng không retry/không thay thế câu trả lời
    max_answer_retries: int = MAX_GROUNDING_RETRIES

    def versions(self) -> dict[str, str]:
        """Trả về thông tin phiên bản prompt/skill/model để gắn vào từng span trace."""
        return resolve_versions(
            prompt_version=self.prompt_version,
            skill_version=self.skill_version,
            model_version=self.model_version or None,
        )

    def get_trace_store(self) -> TraceStore:
        """Lấy TraceStore cô lập đang hoạt động cho lượt chạy hiện tại."""
        active = get_active_trace_store()
        if active is not None:
            return active
        if self.trace_store is not None:
            return self.trace_store
        return TraceStore(versions=self.versions())


def default_deps(*, enable_critic: bool = False, sessions: Any = None) -> Deps:
    """Nối tới hệ thống thật. Graph gọi thẳng các HÀM LÕI trong tools.housing_tools (không qua lớp @tool/JSON)."""
    from core.llm import get_llm
    from core.session_store import SessionStore
    from prompts import BASE_PROMPT, build_advice_prompt, build_decision_prompt
    from safety.grounding import backend_market_fetcher
    from skills.skills_discovery import discover_housing_skills
    from tools.housing_tools import admin_lookup, consult_skill, geocode_point, search_rooms_api

    decision_prompt = build_decision_prompt()
    advice_prompt = build_advice_prompt()

    @lru_cache(maxsize=1)
    def _agent() -> Any:
        from langchain.agents import create_agent
        from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
        from tools.registry import DETAIL_TOOLS

        return create_agent(
            model=get_llm("main"),
            tools=DETAIL_TOOLS,
            system_prompt=decision_prompt,
            middleware=[ModelCallLimitMiddleware(run_limit=MODEL_CALL_LIMIT), ToolCallLimitMiddleware(run_limit=TOOL_CALL_LIMIT)],
        )

    return Deps(
        sessions=sessions if sessions is not None else SessionStore(),
        get_llm=get_llm,
        base_prompt=BASE_PROMPT,
        decision_system_prompt=decision_prompt,
        advice_system_prompt=advice_prompt,
        search_rooms=search_rooms_api,
        geocode=geocode_point,
        admin_lookup=admin_lookup,
        consult_skill=consult_skill,
        skills=discover_housing_skills,
        market_fetcher=backend_market_fetcher,
        decision_agent=_agent,
        enable_critic=enable_critic,
    )
