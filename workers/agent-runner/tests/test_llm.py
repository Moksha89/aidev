"""Unit tests for the LLM JSON parser / fallback path."""

from __future__ import annotations

from agent_runner.llm import _parse_json_loose


def test_parses_raw_json() -> None:
    assert _parse_json_loose('{"a": 1}') == {"a": 1}


def test_strips_markdown_fence() -> None:
    text = '```json\n{"a": 2}\n```'
    assert _parse_json_loose(text) == {"a": 2}


def test_extracts_first_balanced_object() -> None:
    text = "Here you go:\n{\n  \"a\": 3\n}\nThanks!"
    assert _parse_json_loose(text) == {"a": 3}


def test_returns_none_on_garbage() -> None:
    assert _parse_json_loose("not json at all") is None


def test_returns_none_on_partial_json() -> None:
    assert _parse_json_loose('{"a": 1') is None
