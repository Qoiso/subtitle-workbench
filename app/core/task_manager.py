from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable

from app.core.models import TaskRecord, TaskStatus, TaskType


TaskCallback = Callable[[TaskRecord], None]
TaskRunner = Callable[[TaskRecord], Awaitable[dict]]


class TaskManager:
    def __init__(self, merge_concurrency: int = 1, download_concurrency: int = 2) -> None:
        self._records: dict[str, TaskRecord] = {}
        self._on_update: list[TaskCallback] = []
        self._merge_sem = asyncio.Semaphore(merge_concurrency)
        self._download_sem = asyncio.Semaphore(download_concurrency)
        self._active_tasks: dict[str, asyncio.Task] = {}
        self._cancel_reasons: dict[str, str] = {}

    def subscribe(self, callback: TaskCallback) -> None:
        self._on_update.append(callback)

    def _emit(self, record: TaskRecord) -> None:
        for cb in self._on_update:
            cb(record)

    def get(self, task_id: str) -> TaskRecord | None:
        return self._records.get(task_id)

    def submit(self, task_type: TaskType, payload, runner: TaskRunner) -> str:
        task_id = str(uuid.uuid4())
        rec = TaskRecord(task_id=task_id, task_type=task_type, payload=payload, status=TaskStatus.QUEUED)
        self._records[task_id] = rec
        self._emit(rec)
        task = asyncio.create_task(self._run(rec, runner))
        self._active_tasks[task_id] = task
        return task_id

    async def _run(self, rec: TaskRecord, runner: TaskRunner) -> None:
        sem = self._merge_sem if rec.task_type in {TaskType.MERGE, TaskType.SUBTITLE} else self._download_sem
        try:
            async with sem:
                rec.status = TaskStatus.RUNNING
                self._emit(rec)
                rec.result = await runner(rec)
                rec.status = TaskStatus.SUCCESS
                rec.message = "Completed"
                rec.progress = 100.0
                self._emit(rec)
        except asyncio.CancelledError:
            reason = self._cancel_reasons.pop(rec.task_id, "cancel")
            if reason == "pause":
                rec.status = TaskStatus.PAUSED
                rec.message = "Paused"
            else:
                rec.status = TaskStatus.CANCELED
                rec.message = "Canceled"
            self._emit(rec)
            raise
        except Exception as exc:  # noqa: BLE001
            rec.status = TaskStatus.FAILED
            rec.message = str(exc)
            self._emit(rec)
        finally:
            self._active_tasks.pop(rec.task_id, None)
            self._cancel_reasons.pop(rec.task_id, None)

    def update_progress(self, task_id: str, percent: float, message: str = "") -> None:
        rec = self._records.get(task_id)
        if not rec:
            return
        rec.progress = max(0.0, min(100.0, percent))
        if message:
            rec.message = message
        self._emit(rec)

    def set_status(self, task_id: str, status: TaskStatus, message: str = "") -> None:
        rec = self._records.get(task_id)
        if not rec:
            return
        rec.status = status
        if message:
            rec.message = message
        self._emit(rec)

    def cancel(self, task_id: str, reason: str = "cancel") -> bool:
        task = self._active_tasks.get(task_id)
        if not task:
            return False
        self._cancel_reasons[task_id] = reason
        task.cancel()
        return True

