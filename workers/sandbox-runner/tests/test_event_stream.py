"""Event stream publishes JSON envelopes to a Redis pub/sub channel."""

from __future__ import annotations

import json

from sandbox_runner.event_stream import EventStream, SandboxEvent


class _FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []
        self.closed = False

    def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1

    def close(self) -> None:
        self.closed = True


def test_publish_serialises_event_payload() -> None:
    fake = _FakeRedis()
    stream = EventStream(
        redis_url="redis://ignored",
        channel="aidev.test",
        client=fake,
    )
    ok = stream.publish(
        task_id="t1", kind="sandbox.started", payload={"foo": "bar"}
    )
    assert ok is True
    assert len(fake.published) == 1
    channel, body = fake.published[0]
    assert channel == "aidev.test"
    parsed = json.loads(body)
    assert parsed["task_id"] == "t1"
    assert parsed["kind"] == "sandbox.started"
    assert parsed["payload"] == {"foo": "bar"}
    assert isinstance(parsed["timestamp"], float)


def test_publish_swallows_errors_and_returns_false() -> None:
    class _Broken:
        def publish(self, channel: str, message: str) -> int:
            raise RuntimeError("redis down")

        def close(self) -> None:
            pass

    stream = EventStream(
        redis_url="redis://ignored",
        channel="aidev.test",
        client=_Broken(),
    )
    assert stream.publish(task_id="t1", kind="x", payload={}) is False


def test_event_to_json_is_stable() -> None:
    event = SandboxEvent(
        task_id="t1", kind="x", payload={"b": 1, "a": 2}, timestamp=1.0
    )
    body = event.to_json()
    # Keys sorted, compact separators.
    assert (
        body
        == '{"kind":"x","payload":{"a":2,"b":1},"task_id":"t1","timestamp":1.0}'
    )
