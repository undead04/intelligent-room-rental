from __future__ import annotations

from typing import Any, Optional

from langgraph.graph import END, START, StateGraph

from domain.schemas import AgentResponse
from graph.deps import Deps
from graph.nodes.advisory import make_advisory_node
from graph.nodes.clarification import make_clarification_node
from graph.nodes.decision import make_decision_node
from graph.nodes.formatter import make_formatter_node
from graph.nodes.guardrail import make_guardrail_node
from graph.nodes.retrieval import make_retrieval_node
from graph.nodes.understand import make_understand_node
from graph.nodes.verify import make_verify_node
from graph.routing import route_after_guardrail, route_after_understand, route_after_verify
from graph.state import HousingAgentState
from graph.tracing import (
    TraceStore,
    bind_case_id,
    bind_trace_store,
    get_active_case_id,
    reset_case_id,
    reset_trace_store,
)


def build_housing_graph(deps: Deps, checkpointer: Any = None):
    """8 node: guardrail -> understand -> {formatter | decision | advisory | clarification | retrieval} -> decision -> verify -> formatter."""
    g = StateGraph(HousingAgentState)
    g.add_node("guardrail_node", make_guardrail_node(deps))
    g.add_node("understand_node", make_understand_node(deps))
    g.add_node("clarification_node", make_clarification_node(deps))
    g.add_node("advisory_node", make_advisory_node(deps))
    g.add_node("retrieval_node", make_retrieval_node(deps))
    g.add_node("decision_node", make_decision_node(deps))
    g.add_node("verify_node", make_verify_node(deps))
    g.add_node("formatter_node", make_formatter_node(deps))

    g.add_edge(START, "guardrail_node")
    g.add_conditional_edges("guardrail_node", route_after_guardrail, {"formatter_node": "formatter_node", "understand_node": "understand_node"})
    g.add_conditional_edges("understand_node", route_after_understand, {
        "formatter_node": "formatter_node", "decision_node": "decision_node", "advisory_node": "advisory_node",
        "clarification_node": "clarification_node", "retrieval_node": "retrieval_node"})
    g.add_edge("retrieval_node", "decision_node")
    g.add_edge("decision_node", "verify_node")
    g.add_conditional_edges("verify_node", route_after_verify, {"decision_node": "decision_node", "formatter_node": "formatter_node"})
    g.add_edge("advisory_node", "formatter_node")
    g.add_edge("clarification_node", "formatter_node")
    g.add_edge("formatter_node", END)
    return g.compile(checkpointer=checkpointer)


def run_turn(
    graph: Any,
    user_message: str,
    session_id: Optional[str] = None,
    config: Optional[dict] = None,
    *,
    case_id: Optional[str] = None,
    trace_store: Optional[TraceStore] = None,
) -> AgentResponse:
    """Một lượt hội thoại -> AgentResponse (trace cô lập ngoài State, gắn run_id/seq/versions/case_id)."""
    state: dict[str, Any] = {"user_message": user_message}
    if session_id:
        state["session_id"] = session_id
    run_config = config or {}
    eff_case = case_id if case_id is not None else get_active_case_id()
    effective_store = trace_store if trace_store is not None else TraceStore(
        session_id=session_id,
        case_id=eff_case,
    )
    case_tok = bind_case_id(eff_case) if eff_case is not None else None
    store_tok = bind_trace_store(effective_store)
    try:
        return graph.invoke(state, config=run_config)["final_response"]
    finally:
        reset_trace_store(store_tok)
        if case_tok is not None:
            reset_case_id(case_tok)
