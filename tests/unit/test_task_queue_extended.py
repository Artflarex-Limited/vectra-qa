"""
Extended unit tests for the task queue module.

Tests cover:
- RedisTaskQueue operations with mocked redis
- Error handling in queue operations
- Priority ordering edge cases in Redis
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from mcp_server.task_queue import (
    InMemoryTaskQueue,
    RedisTaskQueue,
    get_task_queue,
)

# ──────────────────────────────────────────────
# RedisTaskQueue with mocked redis
# ──────────────────────────────────────────────


class TestRedisTaskQueueOperations:
    """Test RedisTaskQueue operations when Redis is available."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.ping.return_value = True
        return redis

    @pytest.fixture
    def redis_queue(self, mock_redis):
        """Create a RedisTaskQueue with mocked redis."""
        with patch("redis.from_url", return_value=mock_redis):
            queue = RedisTaskQueue("redis://localhost:6379/0")
        return queue

    @pytest.mark.unit
    def test_redis_enqueue_stores_task(self, redis_queue, mock_redis):
        """Should store task data and add to priority queue."""
        task_id = redis_queue.enqueue(
            role="ui_explorer",
            objective="Test homepage",
            memory_node="Runs/Test.md",
            params={"url": "https://example.com"},
            priority=5,
        )

        assert task_id.startswith("task-")
        mock_redis.hset.assert_called_once()
        mock_redis.zadd.assert_called_once()
        # Verify zadd was called with negative priority
        call_args = mock_redis.zadd.call_args
        assert call_args[0][1] == {task_id: -5}

    @pytest.mark.unit
    def test_redis_enqueue_with_fallback(self, redis_queue, mock_redis):
        """Should fallback when redis unavailable during enqueue."""
        redis_queue._available = False
        redis_queue._fallback = InMemoryTaskQueue()

        task_id = redis_queue.enqueue("role", "obj", "node", {}, priority=1)
        assert task_id.startswith("task-")

    @pytest.mark.unit
    def test_redis_dequeue_returns_task(self, redis_queue, mock_redis):
        """Should return task from redis queue."""
        task_data = {
            "id": "task-abc123",
            "type": "ui_explorer",
            "params": {"url": "https://example.com"},
            "role": "ui_explorer",
            "objective": "Test",
            "memory_node": "Runs/Test.md",
            "priority": 5,
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
        }
        mock_redis.zpopmin.return_value = [["task-abc123", -5]]
        mock_redis.hget.return_value = json.dumps(task_data)

        task = redis_queue.dequeue()

        assert task is not None
        assert task.id == "task-abc123"
        assert task.status == "running"
        mock_redis.zpopmin.assert_called_once()
        mock_redis.hset.assert_called_with(
            "vectra:queue:tasks", "task-abc123", json.dumps({**task_data, "status": "running"})
        )

    @pytest.mark.unit
    def test_redis_dequeue_empty_queue(self, redis_queue, mock_redis):
        """Should return None when queue is empty."""
        mock_redis.zpopmin.return_value = []

        result = redis_queue.dequeue()
        assert result is None

    @pytest.mark.unit
    def test_redis_dequeue_missing_task_data(self, redis_queue, mock_redis):
        """Should return None when task data is missing."""
        mock_redis.zpopmin.return_value = [["task-abc123", -5]]
        mock_redis.hget.return_value = None

        result = redis_queue.dequeue()
        assert result is None

    @pytest.mark.unit
    def test_redis_complete_updates_status(self, redis_queue, mock_redis):
        """Should update task status to completed."""
        task_data = {
            "id": "task-abc123",
            "type": "ui_explorer",
            "params": {},
            "role": "ui_explorer",
            "objective": "Test",
            "memory_node": "Runs/Test.md",
            "priority": 0,
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
        }
        mock_redis.hget.return_value = json.dumps(task_data)

        redis_queue.complete("task-abc123", {"passed": True})

        mock_redis.hset.assert_called()
        call_args = mock_redis.hset.call_args
        updated_data = json.loads(call_args[0][2])
        assert updated_data["status"] == "completed"
        assert updated_data["result"] == {"passed": True}

    @pytest.mark.unit
    def test_redis_complete_missing_task(self, redis_queue, mock_redis):
        """Should handle complete when task not found."""
        mock_redis.hget.return_value = None

        redis_queue.complete("task-missing", {"passed": True})
        # Should not raise

    @pytest.mark.unit
    def test_redis_fail_updates_status(self, redis_queue, mock_redis):
        """Should update task status to failed."""
        task_data = {
            "id": "task-abc123",
            "type": "ui_explorer",
            "params": {},
            "role": "ui_explorer",
            "objective": "Test",
            "memory_node": "Runs/Test.md",
            "priority": 0,
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
        }
        mock_redis.hget.return_value = json.dumps(task_data)

        redis_queue.fail("task-abc123", "Something went wrong")

        mock_redis.hset.assert_called()
        call_args = mock_redis.hset.call_args
        updated_data = json.loads(call_args[0][2])
        assert updated_data["status"] == "failed"
        assert updated_data["error"] == "Something went wrong"

    @pytest.mark.unit
    def test_redis_fail_missing_task(self, redis_queue, mock_redis):
        """Should handle fail when task not found."""
        mock_redis.hget.return_value = None

        redis_queue.fail("task-missing", "error")
        # Should not raise

    @pytest.mark.unit
    def test_redis_get_status_returns_task(self, redis_queue, mock_redis):
        """Should return task by id."""
        task_data = {
            "id": "task-abc123",
            "type": "ui_explorer",
            "params": {},
            "role": "ui_explorer",
            "objective": "Test",
            "memory_node": "Runs/Test.md",
            "priority": 0,
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
        }
        mock_redis.hget.return_value = json.dumps(task_data)

        task = redis_queue.get_status("task-abc123")

        assert task is not None
        assert task.id == "task-abc123"

    @pytest.mark.unit
    def test_redis_get_status_missing(self, redis_queue, mock_redis):
        """Should return None for missing task."""
        mock_redis.hget.return_value = None

        result = redis_queue.get_status("task-missing")
        assert result is None

    @pytest.mark.unit
    def test_redis_list_pending_returns_tasks(self, redis_queue, mock_redis):
        """Should return all pending tasks."""
        task_data_1 = {
            "id": "task-abc123",
            "type": "ui_explorer",
            "params": {},
            "role": "ui_explorer",
            "objective": "Test 1",
            "memory_node": "Runs/A.md",
            "priority": 5,
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
        }
        task_data_2 = {
            "id": "task-def456",
            "type": "data_validator",
            "params": {},
            "role": "data_validator",
            "objective": "Test 2",
            "memory_node": "Runs/B.md",
            "priority": 3,
            "created_at": "2025-01-01T00:00:00Z",
            "status": "pending",
        }
        mock_redis.zrange.return_value = ["task-abc123", "task-def456"]
        mock_redis.hget.side_effect = [
            json.dumps(task_data_1),
            json.dumps(task_data_2),
        ]

        tasks = redis_queue.list_pending()

        assert len(tasks) == 2
        assert tasks[0].id == "task-abc123"
        assert tasks[1].id == "task-def456"

    @pytest.mark.unit
    def test_redis_list_pending_empty(self, redis_queue, mock_redis):
        """Should return empty list when no pending tasks."""
        mock_redis.zrange.return_value = []

        tasks = redis_queue.list_pending()
        assert tasks == []

    @pytest.mark.unit
    def test_redis_list_pending_missing_data(self, redis_queue, mock_redis):
        """Should skip tasks with missing data."""
        mock_redis.zrange.return_value = ["task-abc123", "task-def456"]
        mock_redis.hget.side_effect = [
            json.dumps(
                {
                    "id": "task-abc123",
                    "type": "t",
                    "params": {},
                    "role": "r",
                    "objective": "o",
                    "memory_node": "n",
                    "priority": 0,
                    "created_at": "2025-01-01T00:00:00Z",
                    "status": "pending",
                }
            ),
            None,
        ]

        tasks = redis_queue.list_pending()
        assert len(tasks) == 1
        assert tasks[0].id == "task-abc123"

    @pytest.mark.unit
    def test_redis_priority_ordering_high_first(self, redis_queue, mock_redis):
        """Should order by priority with highest first."""
        calls = []

        def capture_zadd(queue_name, mapping):
            calls.append(mapping)

        mock_redis.zadd.side_effect = capture_zadd

        redis_queue.enqueue("role", "Low", "node", {}, priority=1)
        redis_queue.enqueue("role", "High", "node", {}, priority=10)
        redis_queue.enqueue("role", "Medium", "node", {}, priority=5)

        assert list(calls[0].values())[0] == -1
        assert list(calls[1].values())[0] == -10
        assert list(calls[2].values())[0] == -5


class TestRedisTaskQueueErrorHandling:
    """Test RedisTaskQueue error handling."""

    @pytest.mark.unit
    def test_redis_init_import_error(self):
        """Should handle redis import error gracefully."""
        with patch("redis.from_url", side_effect=ImportError("No redis")):
            queue = RedisTaskQueue("redis://localhost:6379/0")
            assert queue._available is False
            assert isinstance(queue._fallback, InMemoryTaskQueue)

    @pytest.mark.unit
    def test_redis_init_connection_error(self):
        """Should handle redis connection error gracefully."""
        with patch("redis.from_url", side_effect=Exception("Connection refused")):
            queue = RedisTaskQueue("redis://localhost:6379/0")
            assert queue._available is False
            assert isinstance(queue._fallback, InMemoryTaskQueue)


class TestRedisTaskQueueFallbackDelegation:
    """Test that all operations delegate to fallback when Redis unavailable."""

    @pytest.mark.unit
    def test_fallback_get_status_delegates(self):
        """Should delegate get_status to fallback."""
        with patch.object(RedisTaskQueue, "__init__", return_value=None):
            queue = RedisTaskQueue.__new__(RedisTaskQueue)
            fallback = MagicMock(spec=InMemoryTaskQueue)
            fallback.get_status.return_value = None
            queue._available = False
            queue._fallback = fallback

        result = queue.get_status("tid")
        assert result is None
        fallback.get_status.assert_called_once_with("tid")

    @pytest.mark.unit
    def test_fallback_list_pending_delegates(self):
        """Should delegate list_pending to fallback."""
        with patch.object(RedisTaskQueue, "__init__", return_value=None):
            queue = RedisTaskQueue.__new__(RedisTaskQueue)
            fallback = MagicMock(spec=InMemoryTaskQueue)
            fallback.list_pending.return_value = []
            queue._available = False
            queue._fallback = fallback

        result = queue.list_pending()
        assert result == []
        fallback.list_pending.assert_called_once()


class TestInMemoryTaskQueuePriorityEdgeCases:
    """Test priority ordering edge cases."""

    @pytest.mark.unit
    def test_same_priority_maintains_fifo(self):
        """Should maintain FIFO order for same priority."""
        queue = InMemoryTaskQueue()
        queue.enqueue("role", "First", "node", {}, priority=5)
        queue.enqueue("role", "Second", "node", {}, priority=5)
        queue.enqueue("role", "Third", "node", {}, priority=5)

        assert queue.dequeue().objective == "First"
        assert queue.dequeue().objective == "Second"
        assert queue.dequeue().objective == "Third"

    @pytest.mark.unit
    def test_negative_priority(self):
        """Should handle negative priorities."""
        queue = InMemoryTaskQueue()
        queue.enqueue("role", "Negative", "node", {}, priority=-5)
        queue.enqueue("role", "Positive", "node", {}, priority=5)
        queue.enqueue("role", "Zero", "node", {}, priority=0)

        assert queue.dequeue().objective == "Positive"
        assert queue.dequeue().objective == "Zero"
        assert queue.dequeue().objective == "Negative"

    @pytest.mark.unit
    def test_mixed_priority_insertions(self):
        """Should correctly order with mixed insertions."""
        queue = InMemoryTaskQueue()
        queue.enqueue("role", "Low", "node", {}, priority=1)
        queue.enqueue("role", "High", "node", {}, priority=100)
        queue.enqueue("role", "Medium", "node", {}, priority=50)
        queue.enqueue("role", "Very High", "node", {}, priority=200)
        queue.enqueue("role", "Very Low", "node", {}, priority=0)

        assert queue.dequeue().objective == "Very High"
        assert queue.dequeue().objective == "High"
        assert queue.dequeue().objective == "Medium"
        assert queue.dequeue().objective == "Low"
        assert queue.dequeue().objective == "Very Low"


class TestTaskQueueFactory:
    """Additional factory tests."""

    @pytest.mark.unit
    def test_get_task_queue_singleton_caching(self):
        """Should cache the queue instance."""
        with patch("mcp_server.task_queue._queue_instance", None):
            with patch("mcp_server.task_queue.os.getenv", return_value=None):
                q1 = get_task_queue()
                q2 = get_task_queue()
                assert q1 is q2

    @pytest.mark.unit
    def test_redis_queue_key_generation(self):
        """Should generate correct redis keys."""
        with patch("redis.from_url") as mock_from_url:
            mock_redis = MagicMock()
            mock_redis.ping.return_value = True
            mock_from_url.return_value = mock_redis
            queue = RedisTaskQueue("redis://localhost:6379/0")
            assert queue._key("tasks") == "vectra:queue:tasks"
            assert queue._key("pending") == "vectra:queue:pending"
