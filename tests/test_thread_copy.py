"""Tests for thread copy with checkpoint data."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from langrove.services.thread_service import ThreadService


def _make_service(checkpointer=None):
    repo = AsyncMock()
    registry = MagicMock()
    registry.list_graphs.return_value = []
    return ThreadService(repo, checkpointer, registry)


class TestThreadCopyNoCheckpointer:
    @pytest.mark.asyncio
    async def test_copy_without_checkpointer_returns_new_thread(self):
        service = _make_service(checkpointer=None)
        source_id = uuid4()
        new_id = uuid4()
        service._repo.copy.return_value = {
            "thread_id": new_id,
            "metadata": {"key": "value"},
            "status": "idle",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

        thread = await service.copy(source_id)

        service._repo.copy.assert_awaited_once_with(source_id)
        assert thread.thread_id == new_id
        assert thread.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_copy_without_checkpointer_no_checkpoint_sql(self):
        service = _make_service(checkpointer=None)
        service._repo.copy.return_value = {
            "thread_id": uuid4(),
            "metadata": {},
            "status": "idle",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }
        # Should not raise even without checkpointer
        await service.copy(uuid4())


class TestThreadCopyWithCheckpointer:
    def _make_mock_checkpointer(self):
        mock_conn = AsyncMock()
        mock_conn_ctx = AsyncMock()
        mock_conn_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn_ctx.__aexit__ = AsyncMock(return_value=None)

        checkpointer = MagicMock()
        checkpointer.conn = MagicMock()
        checkpointer.conn.connection = MagicMock(return_value=mock_conn_ctx)
        return checkpointer, mock_conn

    @pytest.mark.asyncio
    async def test_copy_with_checkpointer_calls_three_inserts(self):
        checkpointer, mock_conn = self._make_mock_checkpointer()
        service = _make_service(checkpointer=checkpointer)
        source_id = uuid4()
        new_id = uuid4()
        service._repo.copy.return_value = {
            "thread_id": new_id,
            "metadata": {},
            "status": "idle",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

        await service.copy(source_id)

        assert mock_conn.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_copy_checkpoint_sql_uses_correct_thread_ids(self):
        checkpointer, mock_conn = self._make_mock_checkpointer()
        service = _make_service(checkpointer=checkpointer)
        source_id = uuid4()
        new_id = uuid4()
        service._repo.copy.return_value = {
            "thread_id": new_id,
            "metadata": {},
            "status": "idle",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

        await service.copy(source_id)

        calls = mock_conn.execute.await_args_list
        assert len(calls) == 3
        for call in calls:
            params = call[0][1]  # second positional arg = params tuple
            assert params[0] == str(new_id)  # dest
            assert params[1] == str(source_id)  # source

    @pytest.mark.asyncio
    async def test_copy_checkpoint_sql_covers_all_tables(self):
        checkpointer, mock_conn = self._make_mock_checkpointer()
        service = _make_service(checkpointer=checkpointer)
        source_id = uuid4()
        new_id = uuid4()
        service._repo.copy.return_value = {
            "thread_id": new_id,
            "metadata": {},
            "status": "idle",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

        await service.copy(source_id)

        sqls = [call[0][0] for call in mock_conn.execute.await_args_list]
        tables = {"checkpoints", "checkpoint_blobs", "checkpoint_writes"}
        for table in tables:
            assert any(table in sql for sql in sqls), f"Missing SQL for table {table}"

    @pytest.mark.asyncio
    async def test_copy_returns_new_thread_not_source(self):
        checkpointer, mock_conn = self._make_mock_checkpointer()
        service = _make_service(checkpointer=checkpointer)
        source_id = uuid4()
        new_id = uuid4()
        service._repo.copy.return_value = {
            "thread_id": new_id,
            "metadata": {"foo": "bar"},
            "status": "idle",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
        }

        thread = await service.copy(source_id)

        assert thread.thread_id == new_id
        assert thread.metadata == {"foo": "bar"}
        assert thread.thread_id != source_id
