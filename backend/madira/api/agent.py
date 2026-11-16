from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI

from madira.rbac import Capability, require

router = APIRouter()

_agent_slot: dict[str, Any] = {"agent": None}


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
        from ag_ui.core import EventType
        from ag_ui_langgraph import add_langgraph_fastapi_endpoint
        from copilotkit import LangGraphAGUIAgent

        from madira.provider_errors import describe_provider_failure
        from madira.tenancy import active_venue_id

        class VenueScopedAgent(LangGraphAGUIAgent):
            async def run(self, input):
                config = dict(self.config or {})
                configurable = dict(config.get("configurable") or {})
                configurable["madira_venue_id"] = str(active_venue_id())
                config["configurable"] = configurable
                self.config = config
                async for event in super().run(input):
                    if getattr(event, "type", None) == EventType.RUN_ERROR:
                        message = getattr(event, "message", "") or ""
                        _status, detail = describe_provider_failure(RuntimeError(message))
                        event = event.model_copy(update={"message": detail})
                    yield event

        agent = VenueScopedAgent(
            name="head_sommelier",
            description="Maison Madira Head Sommelier. Delegates to menu, pairing, list, inventory, training, and supplier specialists.",
            graph=refresh_sommelier_agent(),
        )
        _agent_slot["agent"] = agent
        add_langgraph_fastapi_endpoint(app=app, agent=agent, path="/ag-ui")
    except Exception as exc:  # pragma: no cover - optional bridge
        app.state.agui_error = str(exc)


@router.get("/ag-ui/threads/{thread_id}/messages", dependencies=[require(Capability.AGENT)])
def agui_thread_messages(thread_id: str) -> dict[str, Any]:
    from madira.agents.checkpointer import checkpoint_messages

    return {"messages": checkpoint_messages(thread_id)}
