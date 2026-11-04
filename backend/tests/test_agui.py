"""The mounted AG-UI endpoint finishes a demo run when the graph has a checkpointer."""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from madira.main import app, refresh_sommelier_agent


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        refresh_sommelier_agent()
        yield test_client


def _run(client: TestClient, thread_id: str, text: str, message_id: str) -> list[dict]:
    payload = {
        "threadId": thread_id,
        "runId": str(uuid.uuid4()),
        "messages": [{"id": message_id, "role": "user", "content": text}],
    }
    with client.stream("POST", "/ag-ui", json=payload, timeout=120) as response:
        assert response.status_code == 200, response.read()
        events: list[dict] = []
        for line in response.iter_lines():
            if isinstance(line, bytes):
                line = line.decode()
            if not line or not line.startswith("data:"):
                continue
            events.append(json.loads(line[5:].strip()))
    return events


def _assert_finished(events: list[dict]) -> None:
    types = [event.get("type") for event in events]
    assert types, "AG-UI stream was empty"
    assert "RUN_ERROR" not in types, types
    assert types[-1] == "RUN_FINISHED", types
    text = "".join(event.get("delta") or "" for event in events if event.get("type") == "TEXT_MESSAGE_CONTENT")
    if not text:
        for event in events:
            if event.get("type") != "MESSAGES_SNAPSHOT":
                continue
            for message in event.get("messages") or []:
                if message.get("role") == "assistant" and isinstance(message.get("content"), str):
                    text += message["content"]
    assert "Head Sommelier" in text, types


def test_agent_run_answers_in_demo_with_checkpointer(client: TestClient):
    thread_id = str(uuid.uuid4())
    response = client.post(
        "/agent/run",
        json={"message": "Show the supplier tasting calendar.", "thread_id": thread_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["demo_mode"] is True
    assert body["thread_id"] == thread_id
    assert "Head Sommelier" in body["reply"]
    assert "supplier-scheduler" in [item["subagent"] for item in body["delegation"]]


def test_agui_demo_run_finishes(client: TestClient):
    events = _run(client, str(uuid.uuid4()), "Show the supplier tasting calendar.", "msg-calendar")
    _assert_finished(events)


def test_agui_second_run_on_the_same_thread(client: TestClient):
    thread_id = str(uuid.uuid4())
    first = _run(client, thread_id, "Show the supplier tasting calendar.", "msg-calendar-1")
    _assert_finished(first)
    refresh_sommelier_agent()
    second = _run(client, thread_id, "Show the supplier tasting calendar again.", "msg-calendar-2")
    _assert_finished(second)
