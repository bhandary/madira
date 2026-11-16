from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from madira.agents.orchestrator import invoke_head_sommelier
from madira.rbac import Capability, require

router = APIRouter()

_agent_slot: dict[str, Any] = {"agent": None}


class AgentRunBody(BaseModel):
    message: str
    thread_id: str | None = None


def _sync_agent_graph(agent: Any, graph: Any) -> None:
    """Point the mounted AG-UI agent at a new graph. Requests clone this object."""
    agent.graph = graph
    try:
        from langgraph.graph.state import CompiledStateGraph

        agent.subgraphs = {
            name
            for name, node in graph.nodes.items()
            if isinstance(getattr(node, "bound", None), CompiledStateGraph)
        }
    except Exception:
        pass


def refresh_sommelier_agent() -> Any:
    from madira.agents.orchestrator import build_head_sommelier

    graph = build_head_sommelier()
    agent = _agent_slot.get("agent")
    if agent is not None:
        _sync_agent_graph(agent, graph)
    return graph


def mount_agui(app: FastAPI) -> None:
    try:
        from ag_ui_langgraph import add_langgraph_fastapi_endpoint
        from copilotkit import LangGraphAGUIAgent

        agent = LangGraphAGUIAgent(
            name="head_sommelier",
            description="Maison Madira Head Sommelier. Delegates to menu, pairing, list, inventory, training, and supplier specialists.",
            graph=refresh_sommelier_agent(),
        )
        _agent_slot["agent"] = agent
        add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/ag-ui")
    except Exception as exc:  # pragma: no cover - optional bridge
        app.state.agui_error = str(exc)


@router.post("/agent/run", dependencies=[require(Capability.AGENT)])
def agent_run(body: AgentRunBody) -> dict[str, Any]:
    from madira.provider_errors import describe_provider_failure

    try:
        return invoke_head_sommelier(body.message, thread_id=body.thread_id)
    except HTTPException:
        raise
    except Exception as exc:
        status, detail = describe_provider_failure(exc)
        raise HTTPException(status_code=status, detail=detail) from exc
