from __future__ import annotations

import threading
from typing import Callable, Dict, Iterable, List, Optional

from .nuclei import NucleiRunner, NucleiTask


TaskListener = Callable[[NucleiTask], None]


class TaskManager:
    """Keep track of ongoing nuclei tasks."""

    def __init__(self, runner: Optional[NucleiRunner] = None) -> None:
        self.runner = runner or NucleiRunner()
        self._tasks: Dict[str, NucleiTask] = {}
        self._listeners: List[TaskListener] = []
        self._lock = threading.Lock()

    def add_listener(self, listener: TaskListener) -> None:
        self._listeners.append(listener)

    def remove_listener(self, listener: TaskListener) -> None:
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def notify_listeners(self, task: NucleiTask) -> None:
        for listener in list(self._listeners):
            listener(task)

    def create_task(
        self,
        name: str,
        targets: Iterable[str],
        templates: Iterable[str],
        *,
        binary: str = "nuclei",
        rate_limit: Optional[int] = None,
        concurrency: Optional[int] = None,
        severity: Optional[str] = None,
        dnslog_server: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> NucleiTask:
        template_paths = [self._resolve_template(path) for path in templates]
        task = NucleiTask(
            name=name,
            targets=[target.strip() for target in targets if target.strip()],
            templates=template_paths,
            binary=binary,
            rate_limit=rate_limit,
            concurrency=concurrency,
            severity=severity,
            dnslog_server=dnslog_server,
            proxy=proxy,
        )
        with self._lock:
            self._tasks[task.identifier] = task
        self.runner.run(task, callback=self._on_task_update)
        return task

    def _resolve_template(self, template: str) -> str:
        return template

    def _on_task_update(self, task: NucleiTask) -> None:
        self.notify_listeners(task)
        if task.status in {"completed", "error"}:
            with self._lock:
                self._tasks[task.identifier] = task

    def get_task(self, identifier: str) -> Optional[NucleiTask]:
        with self._lock:
            return self._tasks.get(identifier)

    def list_tasks(self) -> List[NucleiTask]:
        with self._lock:
            return list(self._tasks.values())

    def stop_task(self, identifier: str) -> None:
        self.runner.stop(identifier)

    def clear_finished(self) -> None:
        with self._lock:
            self._tasks = {
                task_id: task
                for task_id, task in self._tasks.items()
                if task.status not in {"completed", "error"}
            }

