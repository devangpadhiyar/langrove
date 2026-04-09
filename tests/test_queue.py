"""Tests for the Celery queue module -- celery_app, publisher, and tasks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCeleryApp:
    """Tests for the Celery application configuration."""

    def test_celery_app_exists(self):
        from langrove.queue.celery_app import app

        assert app is not None
        assert app.main == "langrove"

    def test_dead_letter_stream_constant(self):
        from langrove.queue.celery_app import DEAD_LETTER_STREAM

        assert DEAD_LETTER_STREAM == "langrove:tasks:dead"

    def test_task_acks_late_enabled(self):
        from langrove.queue.celery_app import app

        assert app.conf.task_acks_late is True

    def test_task_reject_on_worker_lost(self):
        from langrove.queue.celery_app import app

        assert app.conf.task_reject_on_worker_lost is True

    def test_prefetch_multiplier_is_one(self):
        from langrove.queue.celery_app import app

        assert app.conf.worker_prefetch_multiplier == 1

    def test_serializer_is_json(self):
        from langrove.queue.celery_app import app

        assert app.conf.task_serializer == "json"
        assert "json" in app.conf.accept_content

    def test_no_result_backend(self):
        from langrove.queue.celery_app import app

        assert app.conf.result_backend is None

    def test_default_queue_name(self):
        from langrove.queue.celery_app import app

        assert app.conf.task_default_queue == "langrove"

    def test_task_routes_configured(self):
        from langrove.queue.celery_app import app

        routes = app.conf.task_routes
        assert "langrove.queue.tasks.handle_run" in routes

    def test_visibility_timeout_gt_task_timeout(self):
        from langrove.queue.celery_app import app
        from langrove.settings import Settings

        settings = Settings()
        visibility = app.conf.broker_transport_options.get("visibility_timeout")
        assert visibility is not None
        assert visibility >= settings.task_timeout_seconds


class TestTaskPublisher:
    """Tests for the TaskPublisher class."""

    def test_publisher_no_args(self):
        from langrove.queue.publisher import TaskPublisher

        publisher = TaskPublisher()
        assert publisher is not None

    @pytest.mark.asyncio
    async def test_publish_calls_apply_async(self):
        from langrove.queue.publisher import TaskPublisher

        publisher = TaskPublisher()

        mock_apply = MagicMock()
        mock_task = MagicMock()
        mock_task.apply_async = mock_apply

        # handle_run is imported lazily inside publish(), so we patch
        # at the tasks module. Settings uses default queue_name="langrove".
        with patch("langrove.queue.tasks.handle_run", mock_task):
            result = await publisher.publish(
                run_id="run-123",
                thread_id="thread-456",
                assistant_id="asst-789",
                graph_id="my_graph",
                input={"messages": [{"role": "user", "content": "hi"}]},
            )

        assert result == "run-123"
        mock_apply.assert_called_once()
        call_kwargs = mock_apply.call_args
        assert call_kwargs.kwargs["task_id"] == "run-123"
        assert call_kwargs.kwargs["queue"] == "langrove"
        payload = call_kwargs.kwargs["kwargs"]
        assert payload["run_id"] == "run-123"
        assert payload["graph_id"] == "my_graph"
        assert payload["thread_id"] == "thread-456"
        assert payload["assistant_id"] == "asst-789"


class TestHandleRunTask:
    """Tests for the handle_run Celery task registration."""

    def test_task_is_registered(self):
        # Importing the tasks module registers the task with the app
        import langrove.queue.tasks  # noqa: F401
        from langrove.queue.celery_app import app

        assert "langrove.queue.tasks.handle_run" in app.tasks

    def test_task_max_retries(self):
        from langrove.queue.tasks import handle_run

        assert handle_run.max_retries == 3

    def test_task_acks_late(self):
        from langrove.queue.tasks import handle_run

        assert handle_run.acks_late is True

    def test_task_reject_on_worker_lost(self):
        from langrove.queue.tasks import handle_run

        # This is set at task level
        assert handle_run.reject_on_worker_lost is True

    def test_task_is_bound(self):
        """Bound tasks have self as first argument for self.retry()."""
        from celery import Task

        from langrove.queue.tasks import handle_run

        assert isinstance(handle_run, Task)


class TestQueueInit:
    """Tests for the queue package __init__.py exports."""

    def test_exports_task_publisher(self):
        from langrove.queue import TaskPublisher

        assert TaskPublisher is not None

    def test_exports_dead_letter_stream(self):
        from langrove.queue import DEAD_LETTER_STREAM

        assert DEAD_LETTER_STREAM == "langrove:tasks:dead"

    def test_exports_celery_app(self):
        from langrove.queue import app

        assert app is not None
        assert app.main == "langrove"


class TestSettings:
    """Tests for queue-related settings."""

    def test_queue_name_default(self):
        from langrove.settings import Settings

        settings = Settings()
        assert settings.queue_name == "langrove"

    def test_no_worker_id_setting(self):
        """worker_id was removed from Settings (auto-generated in worker.py)."""
        from langrove.settings import Settings

        settings = Settings()
        assert not hasattr(settings, "worker_id")

    def test_no_recovery_interval_setting(self):
        """recovery_interval_seconds was removed (no RecoveryMonitor)."""
        from langrove.settings import Settings

        settings = Settings()
        assert not hasattr(settings, "recovery_interval_seconds")

    def test_worker_concurrency_default(self):
        from langrove.settings import Settings

        settings = Settings()
        assert settings.worker_concurrency == 5

    def test_task_timeout_default(self):
        from langrove.settings import Settings

        settings = Settings()
        assert settings.task_timeout_seconds == 900

    def test_max_delivery_attempts_default(self):
        from langrove.settings import Settings

        settings = Settings()
        assert settings.max_delivery_attempts == 3


class TestWorkerModule:
    """Tests for the worker module."""

    def test_run_worker_is_sync(self):
        """run_worker must be a synchronous function (Celery manages its own loop)."""
        import asyncio

        from langrove.worker import run_worker

        assert not asyncio.iscoroutinefunction(run_worker)

    def test_run_worker_signature(self):
        """run_worker accepts worker_id and queues parameters."""
        import inspect

        from langrove.worker import run_worker

        sig = inspect.signature(run_worker)
        params = list(sig.parameters.keys())
        assert "worker_id" in params
        assert "queues" in params


class TestDeadLetterWrite:
    """Tests for the _write_dead_letter helper."""

    @pytest.mark.asyncio
    async def test_write_dead_letter_calls_xadd(self):
        from langrove.queue.tasks import _write_dead_letter

        mock_redis = MagicMock()
        mock_redis.xadd = MagicMock()
        mock_redis.close = MagicMock()

        with patch("redis.from_url", return_value=mock_redis):
            await _write_dead_letter({"run_id": "test-run"})

        mock_redis.xadd.assert_called_once()
        call_args = mock_redis.xadd.call_args
        assert call_args[0][0] == "langrove:tasks:dead"
        mock_redis.close.assert_called_once()
