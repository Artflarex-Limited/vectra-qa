"""
Task Queue for Distributed Workers

Provides a unified task queue interface that supports:
- Redis-backed queue (for distributed/multi-worker setups)
- In-memory queue (fallback for single-instance deployments)

Usage:
    from mcp_server.task_queue import get_task_queue

    queue = get_task_queue()
    queue.enqueue("test_auth_flow", {"login_url": "https://example.com/login"})
    task = queue.dequeue()
"""

import os
import json
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

logger = structlog.get_logger()


@dataclass
class Task:
    """Represents a test task in the queue."""

    id: str
    type: str
    params: Dict[str, Any]
    role: str
    objective: str
    memory_node: str
    priority: int = 0
    created_at: str = ""
    status: str = "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


class TaskQueue:
    """Base task queue interface."""

    def enqueue(
        self, role: str, objective: str, memory_node: str, params: Dict[str, Any], priority: int = 0
    ) -> str:
        """Add a task to the queue. Returns task ID."""
        raise NotImplementedError

    def dequeue(self) -> Optional[Task]:
        """Get the next task from the queue."""
        raise NotImplementedError

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:
        """Mark a task as completed with result."""
        raise NotImplementedError

    def fail(self, task_id: str, error: str) -> None:
        """Mark a task as failed with error."""
        raise NotImplementedError

    def get_status(self, task_id: str) -> Optional[Task]:
        """Get task status by ID."""
        raise NotImplementedError

    def list_pending(self) -> List[Task]:
        """List all pending tasks."""
        raise NotImplementedError


class InMemoryTaskQueue(TaskQueue):
    """In-memory task queue for single-instance deployments."""

    def __init__(self):
        self._queue: List[Task] = []
        self._completed: Dict[str, Task] = {}
        self._lock = False

    def enqueue(
        self, role: str, objective: str, memory_node: str, params: Dict[str, Any], priority: int = 0
    ) -> str:
        task = Task(
            id=f"task-{uuid.uuid4().hex[:8]}",
            type=role,
            params=params,
            role=role,
            objective=objective,
            memory_node=memory_node,
            priority=priority,
        )
        # Insert sorted by priority (higher first)
        inserted = False
        for i, existing in enumerate(self._queue):
            if existing.priority < priority:
                self._queue.insert(i, task)
                inserted = True
                break
        if not inserted:
            self._queue.append(task)

        logger.info("task_enqueued", task_id=task.id, role=role, queue_length=len(self._queue))
        return task.id

    def dequeue(self) -> Optional[Task]:
        if not self._queue:
            return None
        task = self._queue.pop(0)
        task.status = "running"
        logger.info("task_dequeued", task_id=task.id, role=task.role)
        return task

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:
        # Find in queue or completed
        for task in self._completed.values():
            if task.id == task_id:
                task.status = "completed"
                task.result = result
                return
        logger.warning("task_complete_not_found", task_id=task_id)

    def fail(self, task_id: str, error: str) -> None:
        for task in self._completed.values():
            if task.id == task_id:
                task.status = "failed"
                task.error = error
                return
        logger.warning("task_fail_not_found", task_id=task_id)

    def get_status(self, task_id: str) -> Optional[Task]:
        for task in self._queue:
            if task.id == task_id:
                return task
        for task in self._completed.values():
            if task.id == task_id:
                return task
        return None

    def list_pending(self) -> List[Task]:
        return [t for t in self._queue if t.status == "pending"]


class RedisTaskQueue(TaskQueue):
    """Redis-backed task queue for distributed deployments."""

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        try:
            import redis

            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._redis.ping()
            self._available = True
        except (ImportError, Exception) as e:
            logger.error("redis_not_available", error=str(e))
            self._available = False
            self._fallback = InMemoryTaskQueue()

    def _key(self, suffix: str) -> str:
        return f"vectra:queue:{suffix}"

    def enqueue(
        self, role: str, objective: str, memory_node: str, params: Dict[str, Any], priority: int = 0
    ) -> str:
        if not self._available:
            return self._fallback.enqueue(role, objective, memory_node, params, priority)

        task = Task(
            id=f"task-{uuid.uuid4().hex[:8]}",
            type=role,
            params=params,
            role=role,
            objective=objective,
            memory_node=memory_node,
            priority=priority,
        )

        # Store task data
        self._redis.hset(
            self._key("tasks"),
            task.id,
            json.dumps(
                {
                    "id": task.id,
                    "type": task.type,
                    "params": task.params,
                    "role": task.role,
                    "objective": task.objective,
                    "memory_node": task.memory_node,
                    "priority": task.priority,
                    "created_at": task.created_at,
                    "status": "pending",
                }
            ),
        )

        # Add to priority queue (score = -priority so higher priority comes first)
        self._redis.zadd(self._key("pending"), {task.id: -priority})

        logger.info("task_enqueued_redis", task_id=task.id, role=role)
        return task.id

    def dequeue(self) -> Optional[Task]:
        if not self._available:
            return self._fallback.dequeue()

        # Get highest priority task
        result = self._redis.zpopmin(self._key("pending"))
        if not result:
            return None

        task_id = result[0][0]
        task_data = self._redis.hget(self._key("tasks"), task_id)
        if not task_data:
            return None

        data = json.loads(task_data)
        data["status"] = "running"
        self._redis.hset(self._key("tasks"), task_id, json.dumps(data))

        return Task(**data)

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:
        if not self._available:
            return self._fallback.complete(task_id, result)

        task_data = self._redis.hget(self._key("tasks"), task_id)
        if task_data:
            data = json.loads(task_data)
            data["status"] = "completed"
            data["result"] = result
            self._redis.hset(self._key("tasks"), task_id, json.dumps(data))

    def fail(self, task_id: str, error: str) -> None:
        if not self._available:
            return self._fallback.fail(task_id, error)

        task_data = self._redis.hget(self._key("tasks"), task_id)
        if task_data:
            data = json.loads(task_data)
            data["status"] = "failed"
            data["error"] = error
            self._redis.hset(self._key("tasks"), task_id, json.dumps(data))

    def get_status(self, task_id: str) -> Optional[Task]:
        if not self._available:
            return self._fallback.get_status(task_id)

        task_data = self._redis.hget(self._key("tasks"), task_id)
        if task_data:
            return Task(**json.loads(task_data))
        return None

    def list_pending(self) -> List[Task]:
        if not self._available:
            return self._fallback.list_pending()

        task_ids = self._redis.zrange(self._key("pending"), 0, -1)
        tasks = []
        for task_id in task_ids:
            task_data = self._redis.hget(self._key("tasks"), task_id)
            if task_data:
                tasks.append(Task(**json.loads(task_data)))
        return tasks


# Global queue instance
_queue_instance: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """Get or create the global task queue instance."""
    global _queue_instance
    if _queue_instance is None:
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            _queue_instance = RedisTaskQueue(redis_url)
            if not _queue_instance._available:
                logger.warning("redis_unavailable_using_in_memory")
                _queue_instance = InMemoryTaskQueue()
        else:
            _queue_instance = InMemoryTaskQueue()
    return _queue_instance
