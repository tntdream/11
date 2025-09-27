from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional
from uuid import uuid4


class NucleiExecutionError(RuntimeError):
    """Raised when nuclei execution fails."""


@dataclass
class NucleiTargetResult:
    template_id: str
    matched_at: str
    info: Dict[str, Any]
    raw: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "template_id": self.template_id,
            "matched_at": self.matched_at,
            "info": self.info,
            "raw": self.raw,
        }


@dataclass
class NucleiTask:
    name: str
    targets: List[str]
    templates: List[Path]
    binary: str = "nuclei"
    rate_limit: Optional[int] = None
    concurrency: Optional[int] = None
    severity: Optional[str] = None
    dnslog_server: Optional[str] = None
    proxy: Optional[str] = None
    output_path: Optional[Path] = None
    status: str = "pending"
    progress: float = 0.0
    results: List[NucleiTargetResult] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    identifier: str = field(default_factory=lambda: uuid4().hex)

    def build_command(self) -> List[str]:
        command = [self.binary, "-json"]
        if self.rate_limit:
            command.extend(["-rl", str(self.rate_limit)])
        if self.concurrency:
            command.extend(["-c", str(self.concurrency)])
        if self.severity:
            command.extend(["-severity", self.severity])
        if self.proxy:
            command.extend(["-proxy", self.proxy])
        if self.dnslog_server:
            command.extend(["-interactsh-url", self.dnslog_server])
        for template in self.templates:
            command.extend(["-t", str(template)])
        for target in self.targets:
            command.extend(["-target", target])
        if self.output_path:
            command.extend(["-o", str(self.output_path)])
        return command


class NucleiRunner:
    """Manage execution of nuclei tasks."""

    def __init__(self) -> None:
        self._active: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def run(
        self,
        task: NucleiTask,
        *,
        callback: Optional[Callable[[NucleiTask], None]] = None,
        background: bool = True,
    ) -> None:
        """Execute the provided task."""

        if background:
            thread = threading.Thread(target=self._run_task, args=(task, callback), daemon=True)
            thread.start()
        else:
            self._run_task(task, callback)

    def stop(self, identifier: str) -> None:
        with self._lock:
            process = self._active.get(identifier)
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    def _run_task(self, task: NucleiTask, callback: Optional[Callable[[NucleiTask], None]]) -> None:
        try:
            command = task.build_command()
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            task.status = "error"
            task.error = f"Nuclei binary not found: {task.binary}"
            task.finished_at = time.time()
            if callback:
                callback(task)
            raise NucleiExecutionError(task.error) from exc
        except Exception as exc:  # pragma: no cover - defensive programming
            task.status = "error"
            task.error = str(exc)
            task.finished_at = time.time()
            if callback:
                callback(task)
            raise

        task.status = "running"
        task.started_at = time.time()
        self._register_process(task.identifier, process)
        total_targets = max(len(task.targets), 1)
        processed = 0

        try:
            assert process.stdout is not None
            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                info = payload.get("info", {})
                result = NucleiTargetResult(
                    template_id=payload.get("templateID", ""),
                    matched_at=payload.get("matched-at", ""),
                    info=info,
                    raw=payload,
                )
                task.results.append(result)
                processed += 1
                task.progress = min(processed / total_targets, 0.99)
                if callback:
                    callback(task)

            stderr_output = ""
            if process.stderr is not None:
                stderr_output = process.stderr.read()
            return_code = process.wait()
            task.finished_at = time.time()
            if return_code != 0:
                task.status = "error"
                task.error = stderr_output or f"Nuclei exited with code {return_code}"
            else:
                task.status = "completed"
                task.progress = 1.0
        finally:
            self._unregister_process(task.identifier)
            if callback:
                callback(task)

    def _register_process(self, identifier: str, process: subprocess.Popen) -> None:
        with self._lock:
            self._active[identifier] = process

    def _unregister_process(self, identifier: str) -> None:
        with self._lock:
            self._active.pop(identifier, None)


def summarize_results(results: Iterable[NucleiTargetResult]) -> Dict[str, int]:
    summary: Dict[str, int] = {}
    for result in results:
        severity = result.info.get("severity", "unknown")
        summary[severity] = summary.get(severity, 0) + 1
    return summary

