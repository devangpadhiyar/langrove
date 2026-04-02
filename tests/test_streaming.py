"""Tests for SSE formatting -- verifies wire format matches SDK SSEDecoder expectations."""

from __future__ import annotations

from langrove.models.common import StreamPart
from langrove.streaming.formatter import (
    end_event,
    error_event,
    format_sse,
    format_sse_with_id,
    metadata_event,
)


class TestSSEFormatter:
    def test_format_values_event(self):
        part = StreamPart("values", {"messages": [{"role": "user", "content": "hi"}]})
        result = format_sse(part)
        assert result.startswith("event: values\n")
        assert "data: " in result
        assert result.endswith("\n\n")
        assert '"messages"' in result

    def test_format_metadata_event(self):
        part = metadata_event("run-123")
        result = format_sse(part)
        assert "event: metadata\n" in result
        assert '"run_id":"run-123"' in result

    def test_format_end_event(self):
        part = end_event()
        result = format_sse(part)
        assert result == "event: end\ndata: null\n\n"

    def test_format_error_event(self):
        part = error_event("something broke", "details")
        result = format_sse(part)
        assert "event: error\n" in result
        assert '"something broke"' in result

    def test_format_with_id(self):
        part = StreamPart("updates", {"node": {"output": "x"}})
        result = format_sse_with_id(part, "evt-42")
        assert "id: evt-42\n" in result
        assert "event: updates\n" in result

    def test_format_null_data(self):
        part = StreamPart("end", None)
        result = format_sse(part)
        assert "data: null" in result

    def test_format_complex_data(self):
        data = {
            "messages": [
                {"role": "assistant", "content": "Hello!", "id": "msg-1"},
                {"role": "assistant", "content": "How can I help?", "id": "msg-2"},
            ],
            "count": 42,
            "nested": {"key": [1, 2, 3]},
        }
        part = StreamPart("values", data)
        result = format_sse(part)
        assert "event: values\n" in result
        # orjson output should be valid JSON
        import orjson
        data_line = result.split("data: ", 1)[1].split("\n")[0]
        parsed = orjson.loads(data_line)
        assert parsed["count"] == 42

    def test_subgraph_event_name(self):
        """Subgraph events use pipe-delimited names: updates|subgraph_name"""
        part = StreamPart("updates|my_subgraph", {"node": {"data": "x"}})
        result = format_sse(part)
        assert "event: updates|my_subgraph\n" in result

    def test_messages_partial_event(self):
        part = StreamPart("messages/partial", [{"type": "ai", "id": "m1", "content": "Hel"}])
        result = format_sse(part)
        assert "event: messages/partial\n" in result

    def test_messages_complete_event(self):
        part = StreamPart("messages/complete", [{"type": "ai", "id": "m1", "content": "Hello!"}])
        result = format_sse(part)
        assert "event: messages/complete\n" in result

    def test_full_stream_sequence(self):
        """Verify the expected event sequence: metadata -> events -> end"""
        events = [
            metadata_event("run-abc"),
            StreamPart("values", {"messages": []}),
            StreamPart("values", {"messages": [{"role": "assistant", "content": "Hi"}]}),
            end_event(),
        ]
        formatted = [format_sse(e) for e in events]

        # First event is metadata
        assert "event: metadata" in formatted[0]
        # Last event is end
        assert "event: end" in formatted[-1]
        # All events end with double newline
        for f in formatted:
            assert f.endswith("\n\n")
