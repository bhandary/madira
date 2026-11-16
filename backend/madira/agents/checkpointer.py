"""Persistent LangGraph checkpoints. SQLite for tests and CI, Postgres for dev and prod.

Tables are created by the saver's own setup(), not by Alembic. Thread ids are
prefixed with the venue from the run config (or the request context) so one
venue cannot resume another's thread.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from sqlalchemy.engine.url import make_url

from madira.config import DATABASE_URL
from madira.tenancy import active_venue_id

_holder: _Holder | None = None


class _Holder:
    def __init__(self, saver: BaseCheckpointSaver, close) -> None:
        self.saver = saver
        self._close = close

    def close(self) -> None:
        self._close()


class VenueScopedSaver(BaseCheckpointSaver):
    """Prefix checkpoint thread ids with the current venue."""

    def __init__(self, inner: BaseCheckpointSaver) -> None:
        super().__init__(serde=inner.serde)
        self.inner = inner

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.inner.get_tuple(_scope(config))

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        return self.inner.list(
            _scope(config),
            filter=filter,
            before=_scope(before) if before else before,
            limit=limit,
        )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.inner.put(_scope(config), checkpoint, metadata, new_versions)

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.inner.put_writes(_scope(config), writes, task_id, task_path)

    def delete_thread(self, thread_id: str) -> None:
        self.inner.delete_thread(_thread_key(thread_id, str(active_venue_id())))

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ):
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        self.delete_thread(thread_id)


def get_checkpointer() -> BaseCheckpointSaver:
    """Open the process-wide saver and create its tables."""
    global _holder
    if _holder is None:
        _holder = _open()
    return _holder.saver


def thread_message_texts(thread_id: str, venue_id: str | None = None) -> list[str]:
    """Plain text of the checkpointed messages for one venue's thread."""
    return [_message_text(message) for message in _messages(thread_id, venue_id)]


def checkpoint_messages(thread_id: str) -> list[dict[str, Any]]:
    """AG-UI messages for the venue bound on this request. Empty when the thread is not theirs."""
    from ag_ui_langgraph.utils import langchain_messages_to_agui

    messages = _messages(thread_id, None)
    if not messages:
        return []
    dumped: list[dict[str, Any]] = []
    for message in langchain_messages_to_agui(messages):
        dumped.append(message.model_dump(mode="json", by_alias=True, exclude_none=True))
    return dumped


def _messages(thread_id: str, venue_id: str | None) -> list[Any]:
    """Load messages through the graph so delta checkpoints are reconstructed."""
    from madira.agents.orchestrator import build_head_sommelier

    venue = venue_id or str(active_venue_id())
    state = build_head_sommelier().get_state(
        {"configurable": {"thread_id": thread_id, "madira_venue_id": venue}}
    )
    return list((state.values or {}).get("messages") or [])


def _open() -> _Holder:
    if DATABASE_URL.startswith("sqlite"):
        return _open_sqlite(DATABASE_URL)
    if DATABASE_URL.startswith("postgres"):
        return _open_postgres(DATABASE_URL)
    scheme = DATABASE_URL.split(":", 1)[0]
    raise RuntimeError(f"No LangGraph checkpointer for {scheme}")


def _open_sqlite(url: str) -> _Holder:
    from langgraph.checkpoint.sqlite import SqliteSaver

    database = make_url(url).database or ":memory:"
    if database != ":memory:":
        from pathlib import Path

        Path(database).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database, check_same_thread=False)
    inner = SqliteSaver(conn)
    inner.setup()
    return _Holder(VenueScopedSaver(inner), conn.close)


def _open_postgres(url: str) -> _Holder:
    from langgraph.checkpoint.postgres import PostgresSaver

    conninfo = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    context = PostgresSaver.from_conn_string(conninfo)
    inner = context.__enter__()
    inner.setup()

    def close() -> None:
        context.__exit__(None, None, None)

    return _Holder(VenueScopedSaver(inner), close)


def _scope(config: RunnableConfig | None) -> RunnableConfig | None:
    if not config:
        return config
    configurable = dict(config.get("configurable") or {})
    thread_id = configurable.get("thread_id")
    if not thread_id:
        return config
    raw = configurable.get("madira_venue_id")
    venue = str(raw) if raw else str(active_venue_id())
    configurable["thread_id"] = _thread_key(str(thread_id), venue)
    configurable["madira_venue_id"] = venue
    return {**config, "configurable": configurable}


def _thread_key(thread_id: str, venue: str) -> str:
    prefix = f"{venue}:"
    if thread_id.startswith(prefix):
        return thread_id
    return prefix + thread_id


def _message_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
        return " ".join(part for part in parts if part)
    return str(content or "")
