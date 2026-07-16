"""Structured, CSV-extractable logging for the whole ``robot`` package.

Why the stdlib ``logging`` module and not bare ``print``: a research prototype
needs timestamped, machine-parseable traces that (a) survive being interleaved
across the recording / delivery / UI threads, (b) carry a severity level and the
originating function, and (c) load straight into pandas / R for latency
analysis. ``print`` gives none of that reliably - a comma in a message would
wreck a CSV column, there is no timestamp or thread, and stdout is not
thread-safe. The standard-library ``logging`` module is the state-of-the-art
Python answer (levels, thread-safe handlers, pluggable formatters), so we build
on it rather than around it.

Two handlers are attached to the package logger ``robot``:

  * a **console** handler (stderr) with a compact human-readable line, and
  * a **CSV file** handler that writes one RFC-4180 row per event, with the
    columns::

        timestamp,level,logger,function,event,duration_ms,thread,message

    ``timestamp`` is ISO-8601 with milliseconds and a UTC offset; ``duration_ms``
    is filled on function exit (see ``logcall``) and blank otherwise.

Usage
-----
At an application entry point, call ``setup_logging(run_name="mic_remember")``
once - it creates ``robot/state/logs/mic_remember_<YYYYmmdd_HHMMSS>.csv`` (one
file per run, ideal for a per-condition study session).

In any module::

    from robot.core.logsetup import get_logger, logcall

    log = get_logger(__name__)

    @logcall                      # logs "enter" + "exit" with elapsed ms
    def do_work(x):
        log.info("processing", extra={"event": "progress"})
        ...

Loading the CSV later::

    import pandas as pd
    df = pd.read_csv("robot/state/logs/mic_remember_20260716_213500.csv")
    df.groupby("function").duration_ms.describe()

The module installs a ``NullHandler`` on import (the library convention), so
importing it never emits anything or creates files; only ``setup_logging``
attaches real handlers.
"""

from __future__ import annotations

import csv
import functools
import inspect
import io
import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

from robot.paths import LOGS_DIR

PACKAGE_LOGGER = "robot"

# The CSV schema. Kept in one place so the header row and the formatter never
# drift apart.
CSV_COLUMNS = (
    "timestamp",
    "level",
    "logger",
    "function",
    "event",
    "duration_ms",
    "thread",
    "message",
)

# Library convention: a NullHandler so importing the package never emits or
# creates files. propagate=False keeps records off the root logger until (and
# after) setup_logging() attaches our own handlers.
_pkg_logger = logging.getLogger(PACKAGE_LOGGER)
_pkg_logger.addHandler(logging.NullHandler())
_pkg_logger.propagate = False

_setup_lock = threading.Lock()
_configured = False
_csv_path: Path | None = None


class CsvFormatter(logging.Formatter):
    """Render a ``LogRecord`` as a single RFC-4180 CSV row (no trailing newline;
    the handler appends its own terminator).

    Fields are drawn from the record plus three optional ``extra`` attributes:
    ``func`` (overrides the auto-detected function name - needed when a decorator
    wraps the real function), ``event`` (a short machine tag such as
    ``enter``/``exit``/``consent_asked``), and ``duration_ms`` (float).
    """

    def __init__(self) -> None:
        super().__init__()
        # One private buffer + writer per formatter instance. logging serialises
        # emit()->format() under the handler lock, so this is thread-safe as long
        # as the formatter is attached to a single handler.
        self._buf = io.StringIO()
        self._writer = csv.writer(self._buf, quoting=csv.QUOTE_MINIMAL)

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).astimezone().isoformat(
            timespec="milliseconds"
        )
        func = getattr(record, "func", None) or record.funcName
        event = getattr(record, "event", "") or ""
        duration = getattr(record, "duration_ms", None)
        duration_str = f"{duration:.3f}" if isinstance(duration, (int, float)) else ""
        # One row per event: strip embedded newlines so the CSV stays line-oriented.
        message = record.getMessage().replace("\r", " ").replace("\n", " ")
        row = (
            ts,
            record.levelname,
            record.name,
            func,
            event,
            duration_str,
            record.threadName,
            message,
        )
        self._buf.seek(0)
        self._buf.truncate(0)
        self._writer.writerow(row)
        return self._buf.getvalue().rstrip("\r\n")


class HumanFormatter(logging.Formatter):
    """Compact, readable console line: ``HH:MM:SS.mmm L → func: message (Δ ms)``."""

    _ARROWS = {"enter": "→", "exit": "←", "error": "✗"}

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created).astimezone().strftime("%H:%M:%S.%f")[:-3]
        func = getattr(record, "func", None) or record.funcName
        event = getattr(record, "event", "") or ""
        arrow = self._ARROWS.get(event, " ")
        duration = getattr(record, "duration_ms", None)
        tail = f"  (Δ {duration:.1f} ms)" if isinstance(duration, (int, float)) else ""
        return f"{ts} {record.levelname[0]} {arrow} {func}: {record.getMessage()}{tail}"


def setup_logging(
    *,
    run_name: str | None = None,
    level: int | str | None = None,
    file_level: int | str | None = None,
    console: bool = True,
) -> logging.Logger:
    """Attach the console + CSV handlers to the ``robot`` logger (idempotent).

    Call once at an application entry point. Subsequent calls are no-ops and
    return the same logger, so it is safe for a thin wrapper app and the shared
    engine it calls to both invoke it.

    Parameters
    ----------
    run_name
        Prefix for the CSV filename, e.g. ``"mic_remember"`` ->
        ``mic_remember_<timestamp>.csv``. Handy for one file per study condition.
    level
        Console verbosity (``"DEBUG"``/``"INFO"``/... or a ``logging`` constant).
        Defaults to the ``ROBOT_LOG_LEVEL`` env var, else ``INFO``.
    file_level
        CSV-file verbosity. Defaults to ``ROBOT_LOG_FILE_LEVEL`` else ``level`` -
        so the file matches the console (clean: one row per meaningful call plus
        milestones) by default. Set to ``"DEBUG"`` to *also* record the
        fine-grained per-frame / per-audio-block timing from the
        ``@logcall(level=DEBUG)`` hot paths, for a deep-profiling run.
    console
        Set ``False`` to log only to the CSV file (e.g. a headless benchmark).
    """

    global _configured, _csv_path
    with _setup_lock:
        if _configured:
            return _pkg_logger

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"{run_name}_" if run_name else ""
        csv_path = LOGS_DIR / f"{prefix}{stamp}.csv"

        if level is None:
            level = os.environ.get("ROBOT_LOG_LEVEL", "INFO")
        if file_level is None:
            file_level = os.environ.get("ROBOT_LOG_FILE_LEVEL", level)

        _pkg_logger.setLevel(logging.DEBUG)  # handlers do the filtering

        # CSV file handler. Defaults to the console level (INFO) so the file stays
        # clean and analysis-ready (one row per meaningful call + milestones); set
        # ROBOT_LOG_FILE_LEVEL=DEBUG (or pass file_level="DEBUG") to also capture the
        # per-frame / per-audio-block timing from the @logcall(level=DEBUG) hot paths.
        needs_header = not csv_path.exists() or csv_path.stat().st_size == 0
        file_handler = logging.FileHandler(csv_path, encoding="utf-8")
        file_handler.setLevel(file_level)
        file_handler.setFormatter(CsvFormatter())
        if needs_header:
            file_handler.stream.write(",".join(CSV_COLUMNS) + "\n")
            file_handler.stream.flush()
        _pkg_logger.addHandler(file_handler)

        if console:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(level)
            console_handler.setFormatter(HumanFormatter())
            _pkg_logger.addHandler(console_handler)

        _configured = True
        _csv_path = csv_path
        _pkg_logger.info(
            "logging to %s", csv_path,
            extra={"func": "setup_logging", "event": "setup"},
        )
        return _pkg_logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a package child logger. Pass ``__name__`` from a module.

    No side effects - call ``setup_logging()`` at the entry point to actually see
    output. Records from an unconfigured logger are silently dropped (NullHandler).
    """

    if not name or name == PACKAGE_LOGGER:
        return _pkg_logger
    if not name.startswith(PACKAGE_LOGGER + "."):
        name = f"{PACKAGE_LOGGER}.{name}"
    return logging.getLogger(name)


def log_path() -> Path | None:
    """The CSV file for the current run, or ``None`` before ``setup_logging``."""

    return _csv_path


F = TypeVar("F", bound=Callable[..., Any])


def logcall(_fn: F | None = None, *, level: int = logging.INFO, log_result: bool = False) -> Any:
    """Decorator: log an ``enter`` record on call and an ``exit`` record with the
    elapsed wall-clock time (``duration_ms``) on return - or an ``error`` record
    with the elapsed time if the function raises (then re-raises).

    Usable bare (``@logcall``) or parametrised (``@logcall(level=logging.DEBUG)``
    for chatty/inner functions so they land in the CSV but not the console).
    ``log_result=True`` appends the return value's ``repr`` (truncated) to the
    exit message - use only where the result is small and non-sensitive.

    The wrapped function's real ``__module__``/``__qualname__`` are recorded, so
    the CSV ``logger``/``function`` columns are correct despite the wrapper.
    """

    def decorate(fn: F) -> F:
        # get_logger (not logging.getLogger) so a function whose module is run as
        # "__main__" (python -m robot.apps.<app>) still lands under the robot tree.
        logger = get_logger(fn.__module__)
        qualname = fn.__qualname__

        def _exit_message(result: Any) -> str:
            return f"exit -> {result!r:.200}" if log_result else "exit"

        # Async functions (e.g. the BLE coroutines in policy.py) need an async
        # wrapper - a plain wrapper would time only coroutine *creation* (~0 ms)
        # and never see an exception raised inside the awaited body.
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def awrapper(*args: Any, **kwargs: Any) -> Any:
                logger.log(level, "enter", extra={"func": qualname, "event": "enter"})
                start = time.perf_counter()
                try:
                    result = await fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - log then re-raise
                    elapsed_ms = (time.perf_counter() - start) * 1000.0
                    logger.log(
                        logging.ERROR,
                        "raised %s: %s" % (type(exc).__name__, exc),
                        extra={"func": qualname, "event": "error", "duration_ms": elapsed_ms},
                    )
                    raise
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                logger.log(
                    level, _exit_message(result),
                    extra={"func": qualname, "event": "exit", "duration_ms": elapsed_ms},
                )
                return result

            return awrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger.log(level, "enter", extra={"func": qualname, "event": "enter"})
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001 - log then re-raise; let Ctrl-C pass through
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                logger.log(
                    logging.ERROR,
                    "raised %s: %s" % (type(exc).__name__, exc),
                    extra={"func": qualname, "event": "error", "duration_ms": elapsed_ms},
                )
                raise
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.log(
                level, _exit_message(result),
                extra={"func": qualname, "event": "exit", "duration_ms": elapsed_ms},
            )
            return result

        return wrapper  # type: ignore[return-value]

    # Bare @logcall vs parametrised @logcall(...)
    return decorate(_fn) if callable(_fn) else decorate
