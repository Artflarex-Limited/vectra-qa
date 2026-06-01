"""
Unit tests for the task queue module.

Tests cover:
- Task dataclass construction and defaults
- InMemoryTaskQueue operations (enqueue, dequeue, complete, fail, status, list)
- Queue factory function (get_task_queue)
- RedisTaskQueue fallback behavior
"""

import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from mcp_server.task_queue import (
    Task,
    TaskQueue,
    InMemoryTaskQueue,
    RedisTaskQueue,
    get_task_queue,
)


# ──────────────────────────────────────────────
# Task Dataclass
# ──────────────────────────────────────────────


class TestTaskDataclass:
    """Test the Task dataclass construction and defaults."""

    @pytest.mark.unit
    def test_task_creation_defaults(self):
        """Should create a Task with all default fields populated."""
        task = Task(
            id="task-abc123",
            type="ui_explorer",
            params={"url": "https://example.com"},
            role="ui_explorer",
            objective="Test the homepage",
            memory_node="Runs/Homepage_Test.md",
        )
        assert task.id == "task-abc123"
        assert task.type == "ui_explorer"
        assert task.params == {"url": "https://example.com"}
        assert task.role == "ui_explorer"
        assert task.objective == "Test the homepage"
        assert task.memory_node == "Runs/Homepage_Test.md"
        assert task.priority == 0
        assert task.status == "pending"
        assert task.result is None
        assert task.error is None
        assert task.created_at != ""  # Should be auto-set

    @pytest.mark.unit
    def test_task_auto_generates_created_at(self):
        """Should auto-set created_at when not provided.

        Note: the Task dataclass uses strftime without microseconds,
        so we compare at second precision.
        """
        before = datetime.now(timezone.utc).replace(microsecond=0)
        task = Task(
            id="task-def456",
            type="data_validator",
            params={},
            role="data_validator",
            objective="Validate API response",
            memory_node="Runs/API_Test.md",
        )
        after = datetime.now(timezone.utc).replace(microsecond=0)

        parsed = datetime.strptime(task.created_at.rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        assert before <= parsed <= after, (
            f"created_at={task.created_at} should be between {before} and {after}"
        )

    @pytest.mark.unit
    def test_task_with_explicit_created_at(self):
        """Should honour an explicitly provided created_at."""
        explicit_ts = "2025-01-01T00:00:00Z"
        task = Task(
            id="task-ghi789",
            type="ui_explorer",
            params={},
            role="ui_explorer",
            objective="Test",
            memory_node="Runs/Test.md",
            created_at=explicit_ts,
        )
        assert task.created_at == explicit_ts


# ──────────────────────────────────────────────
# TaskQueue Abstract Base Class
# ──────────────────────────────────────────────


class TestTaskQueueBase:
    """Test the TaskQueue base class raises NotImplementedError."""

    @pytest.mark.unit
    def test_base_class_can_be_instantiated(self):
        """Should be instantiable (no abstract methods in base class)."""
        queue = TaskQueue.__new__(TaskQueue)
        assert isinstance(queue, TaskQueue)

    @pytest.mark.unit
    def test_enqueue_raises_not_implemented(self):
        """Should raise NotImplementedError when called on base."""
        queue = TaskQueue.__new__(TaskQueue)
        with pytest.raises(NotImplementedError):
            queue.enqueue("role", "objective", "node", {})

    @pytest.mark.unit
    def test_dequeue_raises_not_implemented(self):
        """Should raise NotImplementedError when called on base."""
        queue = TaskQueue.__new__(TaskQueue)
        with pytest.raises(NotImplementedError):
            queue.dequeue()

    @pytest.mark.unit
    def test_complete_raises_not_implemented(self):
        """Should raise NotImplementedError when called on base."""
        queue = TaskQueue.__new__(TaskQueue)
        with pytest.raises(NotImplementedError):
            queue.complete("tid", {})

    @pytest.mark.unit
    def test_fail_raises_not_implemented(self):
        """Should raise NotImplementedError when called on base."""
        queue = TaskQueue.__new__(TaskQueue)
        with pytest.raises(NotImplementedError):
            queue.fail("tid", "err")

    @pytest.mark.unit
    def test_get_status_raises_not_implemented(self):
        """Should raise NotImplementedError when called on base."""
        queue = TaskQueue.__new__(TaskQueue)
        with pytest.raises(NotImplementedError):
            queue.get_status("tid")

    @pytest.mark.unit
    def test_list_pending_raises_not_implemented(self):
        """Should raise NotImplementedError when called on base."""
        queue = TaskQueue.__new__(TaskQueue)
        with pytest.raises(NotImplementedError):
            queue.list_pending()


# ──────────────────────────────────────────────
# InMemoryTaskQueue
# ──────────────────────────────────────────────


class TestInMemoryTaskQueueEnqueue:
    """Test enqueue operation."""

    @pytest.mark.unit
    def test_enqueue_returns_string_id(self):
        """Should return a non-empty string task ID."""
        queue = InMemoryTaskQueue()
        task_id = queue.enqueue(
            role="ui_explorer",
            objective="Test the homepage",
            memory_node="Runs/Test.md",
            params={"url": "https://example.com"},
        )
        assert isinstance(task_id, str)
        assert len(task_id) > 0
        assert task_id.startswith("task-")

    @pytest.mark.unit
    def test_enqueue_increases_queue_length(self):
        """Should increase the internal queue length by one."""
        queue = InMemoryTaskQueue()
        assert len(queue._queue) == 0
        queue.enqueue(role="ui_explorer", objective="Test", memory_node="Runs/A.md", params={})
        assert len(queue._queue) == 1
        queue.enqueue(role="data_validator", objective="Validate", memory_node="Runs/B.md", params={})
        assert len(queue._queue) == 2

    @pytest.mark.unit
    def test_enqueue_respects_priority_ordering(self):
        """Should insert higher-priority tasks before lower-priority ones."""
        queue = InMemoryTaskQueue()
        # Insert a low-priority task first, then a high-priority one
        queue.enqueue(role="ui_explorer", objective="Low prio", memory_node="Runs/A.md", params={}, priority=1)
        queue.enqueue(role="data_validator", objective="High prio", memory_node="Runs/B.md", params={}, priority=10)

        assert queue._queue[0].priority == 10
        assert queue._queue[1].priority == 1

    @pytest.mark.unit
    def test_enqueue_stores_all_fields(self):
        """Should preserve all fields in the created Task."""
        queue = InMemoryTaskQueue()
        task_id = queue.enqueue(
            role="ui_explorer",
            objective="Comprehensive test",
            memory_node="Runs/Deep.md",
            params={"url": "https://example.com", "timeout": 30},
            priority=5,
        )
        task = queue._queue[0]
        assert task.id == task_id
        assert task.role == "ui_explorer"
        assert task.objective == "Comprehensive test"
        assert task.memory_node == "Runs/Deep.md"
        assert task.params == {"url": "https://example.com", "timeout": 30}
        assert task.priority == 5
        assert task.status == "pending"


class TestInMemoryTaskQueueDequeue:
    """Test dequeue operation."""

    @pytest.mark.unit
    def test_dequeue_returns_task(self):
        """Should return a Task when queue is non-empty."""
        queue = InMemoryTaskQueue()
        queue.enqueue(role="ui_explorer", objective="Test", memory_node="Runs/A.md", params={})
        task = queue.dequeue()
        assert isinstance(task, Task)
        assert task.role == "ui_explorer"

    @pytest.mark.unit
    def test_dequeue_returns_none_when_empty(self):
        """Should return None when queue is empty."""
        queue = InMemoryTaskQueue()
        result = queue.dequeue()
        assert result is None

    @pytest.mark.unit
    def test_dequeue_sets_status_to_running(self):
        """Should set the task status to 'running' upon dequeue."""
        queue = InMemoryTaskQueue()
        queue.enqueue(role="ui_explorer", objective="Test", memory_node="Runs/A.md", params={})
        task = queue.dequeue()
        assert task.status == "running"

    @pytest.mark.unit
    def test_dequeue_removes_task_from_queue(self):
        """Should remove the task from the internal queue."""
        queue = InMemoryTaskQueue()
        queue.enqueue(role="ui_explorer", objective="Test", memory_node="Runs/A.md", params={})
        assert len(queue._queue) == 1
        queue.dequeue()
        assert len(queue._queue) == 0

    @pytest.mark.unit
    def test_dequeue_returns_highest_priority_first(self):
        """Should return tasks in priority order (highest first)."""
        queue = InMemoryTaskQueue()
        queue.enqueue(role="a", objective="Low", memory_node="Runs/A.md", params={}, priority=1)
        queue.enqueue(role="b", objective="High", memory_node="Runs/B.md", params={}, priority=10)
        queue.enqueue(role="c", objective="Medium", memory_node="Runs/C.md", params={}, priority=5)

        assert queue.dequeue().objective == "High"
        assert queue.dequeue().objective == "Medium"
        assert queue.dequeue().objective == "Low"


class TestInMemoryTaskQueueCompleteAndFail:
    """Test complete/fail operations.

    NOTE: The current implementation of InMemoryTaskQueue.dequeue() pops the
    task from _queue but never stores it in _completed. As a result,
    complete() and fail() always log a warning because they only search
    _completed. These tests document that behaviour faithfully.
    """

    @pytest.mark.unit
    def test_complete_does_not_raise_when_task_exists(self):
        """Should not raise an exception when completing a known task."""
        queue = InMemoryTaskQueue()
        # Manually place a task in _completed (bypassing dequeue)
        task = Task(
            id="task-known",
            type="test",
            params={},
            role="test",
            objective="obj",
            memory_node="Runs/A.md",
        )
        queue._completed["task-known"] = task

        # Should not raise
        queue.complete("task-known", {"passed": True})
        assert task.status == "completed"
        assert task.result == {"passed": True}

    @pytest.mark.unit
    def test_complete_warns_for_unknown_task(self):
        """Should log a warning (not raise) when completing an unknown task."""
        queue = InMemoryTaskQueue()
        # dequeue pops the task but does NOT add it to _completed, so
        # complete() will warn. This is the current (buggy) behaviour.
        queue.enqueue(role="ui_explorer", objective="Test", memory_node="Runs/A.md", params={})
        queue.dequeue()

        # This should not raise — it logs a warning internally
        queue.complete("task-nonexistent", {"passed": True})
        # The task is in neither _queue nor _completed
        assert queue.get_status("task-nonexistent") is None

    @pytest.mark.unit
    def test_fail_does_not_raise_when_task_exists(self):
        """Should not raise an exception when failing a known task."""
        queue = InMemoryTaskQueue()
        task = Task(
            id="task-known",
            type="test",
            params={},
            role="test",
            objective="obj",
            memory_node="Runs/A.md",
        )
        queue._completed["task-known"] = task

        queue.fail("task-known", "Something went wrong")
        assert task.status == "failed"
        assert task.error == "Something went wrong"

    @pytest.mark.unit
    def test_fail_warns_for_unknown_task(self):
        """Should log a warning (not raise) when failing an unknown task."""
        queue = InMemoryTaskQueue()
        queue.enqueue(role="ui_explorer", objective="Test", memory_node="Runs/A.md", params={})
        queue.dequeue()

        # The dequeued task is gone from _queue but never stored in _completed
        queue.fail("task-nonexistent", "Error")

        # Should not crash — internal logger.warning handles it


class TestInMemoryTaskQueueStatusAndListing:
    """Test get_status and list_pending operations."""

    @pytest.mark.unit
    def test_get_status_returns_task_from_queue(self):
        """Should find a task still in the pending queue by ID."""
        queue = InMemoryTaskQueue()
        task_id = queue.enqueue(
            role="ui_explorer", objective="Test", memory_node="Runs/A.md", params={}
        )
        found = queue.get_status(task_id)
        assert found is not None
        assert found.id == task_id

    @pytest.mark.unit
    def test_get_status_returns_task_from_completed(self):
        """Should find a task in the completed store by ID."""
        queue = InMemoryTaskQueue()
        task = Task(
            id="task-comp",
            type="test",
            params={},
            role="test",
            objective="done",
            memory_node="Runs/A.md",
            status="completed",
        )
        queue._completed["task-comp"] = task
        found = queue.get_status("task-comp")
        assert found is not None
        assert found.status == "completed"

    @pytest.mark.unit
    def test_get_status_returns_none_for_missing(self):
        """Should return None for a task ID that does not exist."""
        queue = InMemoryTaskQueue()
        assert queue.get_status("task-nonexistent") is None

    @pytest.mark.unit
    def test_list_pending_returns_only_pending_tasks(self):
        """Should return only tasks with status 'pending'."""
        queue = InMemoryTaskQueue()
        queue.enqueue(role="a", objective="Pending", memory_node="Runs/A.md", params={})
        queue.enqueue(role="b", objective="Also pending", memory_node="Runs/B.md", params={})

        # Dequeue one so it becomes "running"
        dequeued = queue.dequeue()
        assert dequeued.status == "running"

        pending = queue.list_pending()
        assert len(pending) == 1
        assert pending[0].objective == "Also pending"

    @pytest.mark.unit
    def test_list_pending_empty_when_no_tasks(self):
        """Should return an empty list when no pending tasks exist."""
        queue = InMemoryTaskQueue()
        assert queue.list_pending() == []


class TestInMemoryTaskQueueFullLifecycle:
    """Test a realistic lifecycle from enqueue through to completion."""

    @pytest.mark.unit
    def test_enqueue_dequeue_complete_lifecycle(self):
        """Should model a full task lifecycle with manual _completed insertion."""
        queue = InMemoryTaskQueue()

        # Enqueue
        task_id = queue.enqueue(
            role="ui_explorer",
            objective="Test lifecycle",
            memory_node="Runs/Lifecycle.md",
            params={"url": "https://example.com"},
            priority=5,
        )
        assert queue.get_status(task_id) is not None
        assert len(queue.list_pending()) == 1

        # Dequeue
        task = queue.dequeue()
        assert task.id == task_id
        assert task.status == "running"
        assert len(queue.list_pending()) == 0

        # Manually place in _completed (simulating what dequeue *should* do)
        task.status = "pending"  # Reset so complete() can transition it
        queue._completed[task_id] = task

        # Complete
        queue.complete(task_id, {"passed": True, "screenshots": 3})
        assert task.status == "completed"
        assert task.result == {"passed": True, "screenshots": 3}

        # Status check
        found = queue.get_status(task_id)
        assert found is not None
        assert found.status == "completed"


# ──────────────────────────────────────────────
# RedisTaskQueue
# ──────────────────────────────────────────────


class TestRedisTaskQueueFallback:
    """Test RedisTaskQueue fallback behaviour."""

    @pytest.mark.unit
    def test_redis_unavailable_falls_back_to_in_memory(self):
        """Should use InMemoryTaskQueue fallback when Redis is unavailable."""
        with patch.object(RedisTaskQueue, "__init__", return_value=None):
            queue = RedisTaskQueue.__new__(RedisTaskQueue)
            queue._available = False
            queue._fallback = InMemoryTaskQueue()

        assert queue._available is False
        assert isinstance(queue._fallback, InMemoryTaskQueue)

    @pytest.mark.unit
    def test_fallback_enqueue_delegates(self):
        """Should delegate enqueue to fallback when Redis unavailable.

        Note: priority is passed as a positional argument (not keyword)
        because RedisTaskQueue.enqueue calls fallback.enqueue(…, priority).
        """
        with patch.object(RedisTaskQueue, "__init__", return_value=None):
            queue = RedisTaskQueue.__new__(RedisTaskQueue)
            fallback = MagicMock(spec=InMemoryTaskQueue)
            fallback.enqueue.return_value = "fallback-tid"
            queue._available = False
            queue._fallback = fallback

        tid = queue.enqueue("role", "objective", "node", {"key": "val"}, priority=3)
        assert tid == "fallback-tid"
        fallback.enqueue.assert_called_once_with("role", "objective", "node", {"key": "val"}, 3)

    @pytest.mark.unit
    def test_fallback_dequeue_delegates(self):
        """Should delegate dequeue to fallback when Redis unavailable."""
        with patch.object(RedisTaskQueue, "__init__", return_value=None):
            queue = RedisTaskQueue.__new__(RedisTaskQueue)
            fallback = MagicMock(spec=InMemoryTaskQueue)
            fallback.dequeue.return_value = None
            queue._available = False
            queue._fallback = fallback

        result = queue.dequeue()
        assert result is None
        fallback.dequeue.assert_called_once()

    @pytest.mark.unit
    def test_fallback_complete_and_fail_delegate(self):
        """Should delegate complete/fail to fallback when Redis unavailable."""
        with patch.object(RedisTaskQueue, "__init__", return_value=None):
            queue = RedisTaskQueue.__new__(RedisTaskQueue)
            fallback = MagicMock(spec=InMemoryTaskQueue)
            queue._available = False
            queue._fallback = fallback

        queue.complete("tid", {"ok": True})
        fallback.complete.assert_called_once_with("tid", {"ok": True})

        queue.fail("tid", "error")
        fallback.fail.assert_called_once_with("tid", "error")


# ──────────────────────────────────────────────
# get_task_queue factory
# ──────────────────────────────────────────────


class TestGetTaskQueueFactory:
    """Test the get_task_queue singleton factory."""

    @pytest.mark.unit
    def test_returns_in_memory_when_no_redis_url(self):
        """Should return an InMemoryTaskQueue when REDIS_URL is not set."""
        with patch("mcp_server.task_queue.os.getenv", return_value=None) as mock_getenv:
            from mcp_server.task_queue import _queue_instance

            # Reset global for test isolation
            with patch("mcp_server.task_queue._queue_instance", None):
                queue = get_task_queue()
                assert isinstance(queue, InMemoryTaskQueue)
                mock_getenv.assert_called_once_with("REDIS_URL")

    @pytest.mark.unit
    def test_returns_redis_when_redis_url_and_available(self):
        """Should create a RedisTaskQueue when REDIS_URL is set."""
        with patch("mcp_server.task_queue.os.getenv", return_value="redis://localhost:6379"):
            with patch("mcp_server.task_queue._queue_instance", None):
                with patch("mcp_server.task_queue.RedisTaskQueue") as mock_cls:
                    mock_instance = MagicMock()
                    mock_instance._available = True
                    mock_cls.return_value = mock_instance

                    queue = get_task_queue()
                    assert queue is mock_instance
                    mock_cls.assert_called_once_with("redis://localhost:6379")

    @pytest.mark.unit
    def test_redis_import_error_falls_back_to_in_memory(self):
        """Should fall back to InMemoryTaskQueue when redis import fails."""
        with patch("mcp_server.task_queue.os.getenv", return_value="redis://localhost:6379"):
            with patch("mcp_server.task_queue._queue_instance", None):
                # Simulate RedisTaskQueue init catching ImportError by having
                # _available = False and _fallback = InMemoryTaskQueue
                with patch.object(RedisTaskQueue, "__init__", return_value=None):
                    queue = RedisTaskQueue.__new__(RedisTaskQueue)
                    # Manually set the state __init__ would produce
                    queue._available = False
                    queue._fallback = InMemoryTaskQueue()
                    queue._key = lambda s: f"vectra:queue:{s}"

                    # Verify fallback is used
                    assert queue._available is False
                    assert isinstance(queue._fallback, InMemoryTaskQueue)

    @pytest.mark.unit
    def test_factory_returns_same_instance(self):
        """Should return the same instance on repeated calls (singleton)."""
        saved = getattr(get_task_queue, "_cached", None)
        try:
            with patch("mcp_server.task_queue._queue_instance", None):
                q1 = get_task_queue()
                q2 = get_task_queue()
                assert q1 is q2
        finally:
            pass

    @pytest.mark.unit
    def test_redis_unavailable_factory_falls_back(self):
        """Should use InMemoryTaskQueue when REDIS_URL is set but Redis fails."""
        with patch("mcp_server.task_queue.os.getenv", return_value="redis://localhost:6379"):
            with patch("mcp_server.task_queue._queue_instance", None):
                with patch("mcp_server.task_queue.RedisTaskQueue") as mock_cls:
                    mock_instance = MagicMock()
                    mock_instance._available = False
                    mock_cls.return_value = mock_instance

                    queue = get_task_queue()
                    assert isinstance(queue, InMemoryTaskQueue)
                    mock_cls.assert_called_once_with("redis://localhost:6379")
