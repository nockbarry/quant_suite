"""Background task manager for web dashboard operations.

Provides an in-memory task registry backed by ThreadPoolExecutor
so that long-running operations (data refresh, research cycles)
can be triggered from the UI without blocking requests.
"""

import asyncio
import subprocess
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskStatus:
    id: str
    name: str
    state: TaskState = TaskState.PENDING
    submitted_at: datetime = field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or datetime.utcnow()
        start = self.started_at or self.submitted_at
        return (end - start).total_seconds()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "state": self.state.value,
            "submitted_at": self.submitted_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "elapsed": f"{self.elapsed_seconds:.1f}s",
            "result": str(self.result)[:200] if self.result else None,
            "error": self.error,
        }


class TaskManager:
    """In-memory background task executor."""

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, TaskStatus] = {}
        self._lock = threading.Lock()

    def submit_task(self, name: str, fn: Callable, *args, **kwargs) -> str:
        """Submit a callable for background execution. Returns task_id."""
        self._cleanup_old()

        task_id = uuid.uuid4().hex[:12]
        status = TaskStatus(id=task_id, name=name)

        with self._lock:
            self._tasks[task_id] = status

        self._executor.submit(self._run_wrapper, task_id, fn, args, kwargs)
        return task_id

    def submit_async_task(self, name: str, coro_fn: Callable, *args, **kwargs) -> str:
        """Submit an async callable. Runs in a new event loop in a thread."""

        def _run_in_loop():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro_fn(*args, **kwargs))
            finally:
                loop.close()

        return self.submit_task(name, _run_in_loop)

    def submit_subprocess(self, name: str, cmd: list[str], timeout: int = 300) -> str:
        """Submit a subprocess command for background execution."""

        def _run_subprocess():
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd="/home/nock/projects/quant_suite",
                env={"PYTHONPATH": ".", "PATH": "/usr/local/bin:/usr/bin:/bin",
                     "HOME": "/home/nock"},
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr[:500] or f"Exit code {result.returncode}")
            return result.stdout[:500] if result.stdout else "Completed"

        return self.submit_task(name, _run_subprocess)

    def get_task(self, task_id: str) -> TaskStatus | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_active(self) -> list[TaskStatus]:
        with self._lock:
            return [
                t for t in self._tasks.values()
                if t.state in (TaskState.PENDING, TaskState.RUNNING)
            ]

    def list_recent(self, limit: int = 10) -> list[TaskStatus]:
        with self._lock:
            tasks = sorted(self._tasks.values(), key=lambda t: t.submitted_at, reverse=True)
            return tasks[:limit]

    def active_count(self) -> int:
        with self._lock:
            return sum(
                1 for t in self._tasks.values()
                if t.state in (TaskState.PENDING, TaskState.RUNNING)
            )

    def _run_wrapper(self, task_id: str, fn: Callable, args: tuple, kwargs: dict):
        with self._lock:
            task = self._tasks[task_id]
            task.state = TaskState.RUNNING
            task.started_at = datetime.utcnow()

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                task.state = TaskState.COMPLETED
                task.completed_at = datetime.utcnow()
                task.result = result
        except Exception as e:
            with self._lock:
                task.state = TaskState.FAILED
                task.completed_at = datetime.utcnow()
                task.error = str(e)[:500]

    def _cleanup_old(self):
        """Remove completed tasks older than 1 hour."""
        cutoff = datetime.utcnow() - timedelta(hours=1)
        with self._lock:
            to_remove = [
                tid for tid, t in self._tasks.items()
                if t.state in (TaskState.COMPLETED, TaskState.FAILED)
                and t.completed_at
                and t.completed_at < cutoff
            ]
            for tid in to_remove:
                del self._tasks[tid]


# Singleton
_task_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManager()
    return _task_manager
