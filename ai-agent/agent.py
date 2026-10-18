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
from skill_catalog import Catalog, scan_skills
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


def load_catalog() -> Catalog:
    return scan_skills(paths.SKILLS_DIR)


def capabilities() -> dict:
    catalog = load_catalog()
    return {
        "tools": [t.name for t in TOOLS],
        "skills": catalog.metadata(),
        "skill_diagnostics": catalog.diagnostics,
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
            ModelCallLimitMiddleware(run_limit=MODEL_CALL_LIMIT, exit_behavior="end"),
            ToolCallLimitMiddleware(run_limit=TOOL_CALL_LIMIT),
            ObserverMiddleware(),
        ],
    )
