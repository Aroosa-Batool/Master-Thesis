"""Best-effort telemetry for the local thesis presentation console.

The research engines remain authoritative.  This module is deliberately a
no-op unless the presentation server supplies a loopback URL and a per-run
token.  Events and JPEG frames are posted on a small daemon thread; a slow or
closed browser can therefore never delay sensing, consent, or delivery.
"""

from __future__ import annotations

import json
import atexit
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Any


URL_ENV = "THESIS_UI_URL"
TOKEN_ENV = "THESIS_UI_TOKEN"


class _Transport:
    def __init__(self) -> None:
        self.base_url = os.environ.get(URL_ENV, "").rstrip("/")
        self.token = os.environ.get(TOKEN_ENV, "")
        self.enabled = self.base_url.startswith("http://127.0.0.1:") and bool(self.token)
        self._queue: queue.Queue[tuple[str, bytes, dict[str, str]]] = queue.Queue(maxsize=48)
        self._thread: threading.Thread | None = None
        self._last_frame_at = 0.0
        self._start_lock = threading.Lock()

    def _start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        with self._start_lock:
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run,
                    daemon=True,
                    name="thesis-ui-telemetry",
                )
                self._thread.start()

    def enqueue(self, path: str, body: bytes, headers: dict[str, str]) -> None:
        if not self.enabled:
            return
        self._start()
        try:
            self._queue.put_nowait((path, body, headers))
        except queue.Full:
            # Telemetry is explanatory only. Drop stale visual data rather than
            # ever blocking the real privacy pipeline.
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                return
            try:
                self._queue.put_nowait((path, body, headers))
            except queue.Full:
                pass

    def event(self, event_type: str, **payload: Any) -> None:
        body = json.dumps(
            {"type": event_type, "at": time.time(), **payload},
            ensure_ascii=False,
        ).encode("utf-8")
        self.enqueue(
            "/api/internal/event",
            body,
            {"Content-Type": "application/json; charset=utf-8"},
        )

    def frame(self, frame, *, max_fps: float = 6.0) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        if now - self._last_frame_at < 1.0 / max(max_fps, 0.1):
            return
        self._last_frame_at = now
        try:
            import cv2

            ok, encoded = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 78]
            )
            if not ok:
                return
            body = encoded.tobytes()
        except Exception:
            return
        self.enqueue(
            "/api/internal/frame",
            body,
            {"Content-Type": "image/jpeg"},
        )

    def _run(self) -> None:
        while True:
            path, body, headers = self._queue.get()
            request = urllib.request.Request(
                self.base_url + path,
                data=body,
                method="POST",
                headers={**headers, "X-Thesis-Token": self.token},
            )
            try:
                with urllib.request.urlopen(request, timeout=0.75):
                    pass
            except (OSError, urllib.error.URLError):
                pass
            finally:
                self._queue.task_done()

    def flush(self, timeout: float = 1.5) -> None:
        deadline = time.monotonic() + timeout
        while self.enabled and self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.02)


_TRANSPORT = _Transport()
atexit.register(_TRANSPORT.flush)


def enabled() -> bool:
    return _TRANSPORT.enabled


def emit(event_type: str, **payload: Any) -> None:
    _TRANSPORT.event(event_type, **payload)


def stage(step: str, status: str, detail: str, **payload: Any) -> None:
    emit("stage", step=step, status=status, detail=detail, **payload)


def sensor(name: str, active: bool, **payload: Any) -> None:
    emit("sensor", sensor=name, active=active, **payload)


def metric(name: str, value: Any, **payload: Any) -> None:
    emit("metric", name=name, value=value, **payload)


def frame(image, *, max_fps: float = 6.0) -> None:
    _TRANSPORT.frame(image, max_fps=max_fps)


def clear_frame() -> None:
    emit("frame_clear")


def flush(timeout: float = 1.5) -> None:
    _TRANSPORT.flush(timeout)
