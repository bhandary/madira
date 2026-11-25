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


def _run_text(payload: Any) -> str:
    messages = getattr(payload, "messages", None) or []
    parts: list[str] = []
    for msg in messages:
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
    return "\n".join(parts)[-4000:]


def mount_agui(app: FastAPI) -> None:
    try:
        from ag_ui.core import EventType
        from ag_ui_langgraph import add_langgraph_fastapi_endpoint
        from copilotkit import LangGraphAGUIAgent

        from madira.provider_errors import describe_provider_failure
        from madira.tenancy import active_venue_id

        class VenueScopedAgent(LangGraphAGUIAgent):
            async def run(self, input):
                import time

                from ag_ui.core import RunErrorEvent

                from madira.agents import tracker
                from madira.domain.usage.service import UsageError, begin_run, finish_run

                venue_id = active_venue_id()
                message = _run_text(input)
                try:
                    run_id = begin_run(venue_id, message)
                except UsageError as exc:
                    yield RunErrorEvent(message=exc.message, code="usage_limit")
                    return
                started = time.perf_counter()
                tracker.start_run()
                config = dict(self.config or {})
                configurable = dict(config.get("configurable") or {})
                configurable["madira_venue_id"] = str(venue_id)
                config["configurable"] = configurable
                self.config = config
                reply_parts: list[str] = []
                try:
                    async for event in super().run(input):
                        if getattr(event, "type", None) == EventType.RUN_ERROR:
                            error_text = getattr(event, "message", "") or ""
                            _status, detail = describe_provider_failure(RuntimeError(error_text))
                            event = event.model_copy(update={"message": detail})
                        delta = getattr(event, "delta", None)
                        if isinstance(delta, str):
                            reply_parts.append(delta)
                        yield event
                finally:
                    reply = "".join(reply_parts)
                    names = [item.get("subagent", "") for item in tracker.snapshot()["delegation"]]
                    try:
                        finish_run(
                            run_id,
                            reply=reply,
                            delegated=names,
                            latency_ms=int((time.perf_counter() - started) * 1000),
                            tokens_in=max(1, len(message) // 4) if message.strip() else 0,
                            tokens_out=max(1, len(reply) // 4) if reply.strip() else 0,
                        )
                    except Exception:
                        pass

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
