from __future__ import annotations

import json
from io import StringIO

from atlas_weave.events import EventEmitter


def make_emitter() -> tuple[EventEmitter, StringIO]:
    stream = StringIO()
    return EventEmitter(run_id="r1", stream=stream), stream


def parse(stream: StringIO) -> list[dict]:
    stream.seek(0)
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def test_emit_base() -> None:
    emitter, stream = make_emitter()
    emitter.emit("custom", key="val")
    events = parse(stream)
    assert len(events) == 1
    assert events[0]["type"] == "custom"
    assert events[0]["run_id"] == "r1"
    assert events[0]["key"] == "val"
    assert "timestamp" in events[0]


def test_node_started() -> None:
    emitter, stream = make_emitter()
    emitter.node_started("agent_a")
    event = parse(stream)[0]
    assert event["type"] == "node_started"
    assert event["node_id"] == "agent_a"


def test_node_completed() -> None:
    emitter, stream = make_emitter()
    emitter.node_completed("agent_a", duration_ms=150, summary={"ok": True})
    event = parse(stream)[0]
    assert event["type"] == "node_completed"
    assert event["duration_ms"] == 150
    assert event["summary"] == {"ok": True}


def test_node_failed() -> None:
    emitter, stream = make_emitter()
    emitter.node_failed("agent_a", error="boom")
    event = parse(stream)[0]
    assert event["type"] == "node_failed"
    assert event["error"] == "boom"


def test_node_skipped() -> None:
    emitter, stream = make_emitter()
    emitter.node_skipped("agent_a", message="dep failed")
    event = parse(stream)[0]
    assert event["type"] == "node_skipped"
    assert event["message"] == "dep failed"


def test_node_cancelled() -> None:
    emitter, stream = make_emitter()
    emitter.node_cancelled("agent_a", message="user cancelled")
    event = parse(stream)[0]
    assert event["type"] == "node_cancelled"
    assert event["message"] == "user cancelled"


def test_progress() -> None:
    emitter, stream = make_emitter()
    emitter.progress("agent_a", 0.5, "halfway")
    event = parse(stream)[0]
    assert event["type"] == "node_progress"
    assert event["progress"] == 0.5
    assert event["message"] == "halfway"


def test_log() -> None:
    emitter, stream = make_emitter()
    emitter.log("agent_a", "info", "doing stuff")
    event = parse(stream)[0]
    assert event["type"] == "node_log"
    assert event["level"] == "info"
    assert event["message"] == "doing stuff"


def test_graph_patch() -> None:
    emitter, stream = make_emitter()
    emitter.graph_patch(
        nodes=[{"id": "new_node", "label": "New"}],
        edges=[("a", "b")],
    )
    event = parse(stream)[0]
    assert event["type"] == "graph_patch"
    assert event["nodes"] == [{"id": "new_node", "label": "New"}]
    assert event["edges"] == [["a", "b"]]


def test_tool_call() -> None:
    emitter, stream = make_emitter()
    emitter.tool_call("agent_a", tool="http", request_id="req1", input={"url": "https://x.com"})
    event = parse(stream)[0]
    assert event["type"] == "tool_call"
    assert event["tool"] == "http"
    assert event["request_id"] == "req1"


def test_tool_result_with_optional_fields() -> None:
    emitter, stream = make_emitter()
    emitter.tool_result(
        "agent_a", tool="http", request_id="req1",
        output={"status": 200}, duration_ms=50,
        cache_hit=True, error="partial",
    )
    event = parse(stream)[0]
    assert event["type"] == "tool_result"
    assert event["cache_hit"] is True
    assert event["error"] == "partial"
    assert event["duration_ms"] == 50


def test_tool_result_without_optional_fields() -> None:
    emitter, stream = make_emitter()
    emitter.tool_result(
        "agent_a", tool="http", request_id="req1",
        output={"status": 200}, duration_ms=50,
    )
    event = parse(stream)[0]
    assert "cache_hit" not in event
    assert "error" not in event


def test_llm_call_with_prompt_tokens() -> None:
    emitter, stream = make_emitter()
    emitter.llm_call(
        "agent_a", provider="openrouter", model="gpt-4o",
        request_id="llm1", input={"messages": []},
        prompt_tokens=100,
    )
    event = parse(stream)[0]
    assert event["type"] == "llm_call"
    assert event["prompt_tokens"] == 100
    assert event["provider"] == "openrouter"


def test_llm_call_without_prompt_tokens() -> None:
    emitter, stream = make_emitter()
    emitter.llm_call(
        "agent_a", provider="openrouter", model="gpt-4o",
        request_id="llm1", input={"messages": []},
    )
    event = parse(stream)[0]
    assert "prompt_tokens" not in event


def test_llm_result_with_optional_fields() -> None:
    emitter, stream = make_emitter()
    emitter.llm_result(
        "agent_a", provider="openrouter", model="gpt-4o",
        request_id="llm1", output={"text": "hi"},
        duration_ms=200, completion_tokens=45,
        estimated_cost_usd=0.001, prompt_tokens=100, error="trunc",
    )
    event = parse(stream)[0]
    assert event["type"] == "llm_result"
    assert event["prompt_tokens"] == 100
    assert event["error"] == "trunc"
    assert event["completion_tokens"] == 45


def test_llm_result_without_optional_fields() -> None:
    emitter, stream = make_emitter()
    emitter.llm_result(
        "agent_a", provider="openrouter", model="gpt-4o",
        request_id="llm1", output={"text": "hi"},
        duration_ms=200, completion_tokens=45,
        estimated_cost_usd=0.001,
    )
    event = parse(stream)[0]
    assert "prompt_tokens" not in event
    assert "error" not in event


def test_run_completed() -> None:
    emitter, stream = make_emitter()
    emitter.run_completed(summary={"completed_nodes": 3})
    event = parse(stream)[0]
    assert event["type"] == "run_completed"
    assert event["summary"]["completed_nodes"] == 3


def test_run_failed() -> None:
    emitter, stream = make_emitter()
    emitter.run_failed(error="agent_a: boom")
    event = parse(stream)[0]
    assert event["type"] == "run_failed"
    assert event["error"] == "agent_a: boom"


def test_run_cancelled() -> None:
    emitter, stream = make_emitter()
    emitter.run_cancelled(message="user cancelled")
    event = parse(stream)[0]
    assert event["type"] == "run_cancelled"
    assert event["message"] == "user cancelled"


def test_hooks_callback_invocation() -> None:
    captured: list[dict] = []
    stream = StringIO()
    emitter = EventEmitter(run_id="r1", stream=stream, hooks=[captured.append])
    emitter.node_started("agent_a")
    assert len(captured) == 1
    assert captured[0]["type"] == "node_started"
    assert captured[0]["run_id"] == "r1"


def test_multiple_emits_produce_newline_delimited_json() -> None:
    emitter, stream = make_emitter()
    emitter.node_started("a")
    emitter.node_completed("a", duration_ms=10, summary={})
    emitter.run_completed(summary={"completed_nodes": 1})
    events = parse(stream)
    assert len(events) == 3
    assert [e["type"] for e in events] == ["node_started", "node_completed", "run_completed"]
