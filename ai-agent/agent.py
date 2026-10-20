"""LangChain agent cho Smart Housing Decision Support System:
Native housing tools + structured decision support.
"""

from __future__ import annotations

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langchain_openai import ChatOpenAI

import paths
from config import MODEL_CALL_LIMIT, TOOL_CALL_LIMIT, Settings
from observer import ObserverMiddleware
from prompts import build_system_prompt
from skills_discovery import discover_housing_skills
from tools.registry import ALL_TOOLS

# Tập hợp toàn bộ công cụ dùng chung cho monolithic fallback / catalog
TOOLS = ALL_TOOLS


def build_model(settings: Settings) -> ChatOpenAI:
    kwargs = {"model": settings.model_name, "api_key": settings.api_key}
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return ChatOpenAI(**kwargs)


def system_prompt() -> str:
    import importlib
    import prompts as _prompts_mod
    importlib.reload(_prompts_mod)
    return _prompts_mod.build_system_prompt()


def capabilities() -> dict:
    skills_dict = discover_housing_skills()
    return {
        "tools": [t.name for t in TOOLS],
        "skills": [s.__dict__ for s in skills_dict.values()],
        "skill_diagnostics": [],
        "system": "Homigo Smart Housing Decision Support Agent",
    }


def build_agent(model):
    import importlib
    import tools.housing_tools as _ht
    import tools.registry as _reg
    importlib.reload(_ht)
    importlib.reload(_reg)
    return create_agent(
        model=model,
        tools=_reg.ALL_TOOLS,
        system_prompt=system_prompt(),
        middleware=[
            ObserverMiddleware(),
            ModelCallLimitMiddleware(run_limit=MODEL_CALL_LIMIT),
            ToolCallLimitMiddleware(run_limit=TOOL_CALL_LIMIT),
        ],
    )
