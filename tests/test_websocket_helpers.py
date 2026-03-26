"""Tests for websocket helper functions."""

import json

from hive.server.websocket import _extract_thinking, _fallback_title, _strip_large_widget_data


class TestExtractThinking:
    def test_no_thinking(self):
        clean, thinking = _extract_thinking("Hello world")
        assert clean == "Hello world"
        assert thinking is None

    def test_single_block(self):
        clean, thinking = _extract_thinking("<think>reasoning</think>Answer")
        assert clean == "Answer"
        assert thinking == "reasoning"

    def test_multiple_blocks(self):
        clean, thinking = _extract_thinking(
            "<think>step 1</think> mid <think>step 2</think>end"
        )
        assert clean == "mid end"
        assert "step 1" in thinking
        assert "step 2" in thinking

    def test_empty_think_block(self):
        clean, thinking = _extract_thinking("<think></think>result")
        assert clean == "result"
        assert thinking == ""


class TestFallbackTitle:
    def test_simple(self):
        assert _fallback_title("find all GFP plasmids") == "find all GFP plasmids"

    def test_strips_slash(self):
        title = _fallback_title("/search ampicillin")
        assert not title.startswith("/")

    def test_max_4_words(self):
        title = _fallback_title("one two three four five six")
        assert len(title.split()) <= 4

    def test_max_40_chars(self):
        title = _fallback_title("a" * 100)
        assert len(title) <= 40

    def test_empty(self):
        assert _fallback_title("") == "New Chat"
        assert _fallback_title("   ") == "New Chat"


class TestStripLargeWidgetData:
    def test_no_widget(self):
        msg = {"role": "assistant", "content": "hi"}
        result = _strip_large_widget_data(msg, 100)
        assert result == msg

    def test_small_widget_preserved(self):
        msg = {
            "role": "assistant",
            "content": "",
            "widget": {"tool": "gc", "params": {}, "data": {"gc_percent": 50}},
        }
        result = _strip_large_widget_data(msg, 10000)
        assert result["widget"]["data"] == {"gc_percent": 50}

    def test_large_widget_stripped(self):
        big_data = {"results": [{"x": "y" * 200}] * 10}
        msg = {
            "role": "assistant",
            "content": "",
            "widget": {"tool": "search", "params": {"q": "test"}, "data": big_data},
        }
        result = _strip_large_widget_data(msg, 100)
        assert result["widget"].get("stale") is True
        assert "data" not in result["widget"]

    def test_form_never_stripped(self):
        msg = {
            "role": "assistant",
            "content": "",
            "widget": {"type": "form", "tool": "blast", "data": {"x": "y" * 1000}},
        }
        result = _strip_large_widget_data(msg, 10)
        assert result["widget"]["data"] is not None

    def test_python_never_stripped(self):
        msg = {
            "role": "assistant",
            "content": "",
            "widget": {"tool": "python", "data": {"big": "x" * 1000}},
        }
        result = _strip_large_widget_data(msg, 10)
        assert result["widget"]["data"] is not None
