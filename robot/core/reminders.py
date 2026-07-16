"""Time-based reminder store - the trigger for the whole pipeline.

A *reminder* is a piece of private content the owner asked the robot to
hold - e.g. "a doctor's appointment on July 20th at 3 PM" - together with
the time it becomes due and whether it is sensitive. When due, it is
delivered under a presence-gated consent policy:

  - owner alone (no bystander seen/heard): deliver it right away, because
    there is no one to overhear;
  - a bystander is present: ask the watch first (Yes -> disclose aloud,
    No -> show it privately on the wrist).

Reminders are added by ``add_reminder.py`` (spoken) and consumed by both
the voice apps (``mic_remember.py`` / ``mic_reask.py``) and the camera apps
(``camera_remember.py`` / ``camera_reask.py``). Storage mirrors
``ConsentStore`` / ``OwnerStore``: a single JSON file, whole-file atomic writes,
thread-safe, so it survives restarts.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Reminder:
    """One scheduled piece of private content."""

    id: str
    text: str            # what to disclose, e.g. "doctor's appointment at 3 PM"
    remind_at: str       # ISO-8601 local datetime the reminder becomes due
    delivered: bool = False
    # Whether this reminder is sensitive (health/finance/personal). Set by the
    # AI sensitivity classifier when the reminder is added (see sensitivity.py):
    #   True  -> presence-gated, ask watch consent before speaking aloud;
    #   False -> speak normally even with a bystander around.
    # ``None`` means "not yet classified" - the delivery runner classifies it on
    # the fly then, so reminders saved before this field existed still work.
    sensitive: bool | None = None

    @property
    def remind_at_dt(self) -> datetime.datetime:
        return datetime.datetime.fromisoformat(self.remind_at)

    def is_due(self, now: datetime.datetime) -> bool:
        """True if this reminder is undelivered and its time has arrived."""

        return (not self.delivered) and now >= self.remind_at_dt


class ReminderStore:
    """JSON-backed list of reminders, thread-safe and crash-safe.

    ``add`` from the setup script and ``due``/``mark_delivered`` from the
    running demo's main + worker threads all take the same lock; writes go
    through a same-directory temp file + ``os.replace`` so a crash mid-write
    can never leave half a JSON file on disk (same approach as ConsentStore).
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._items: dict[str, Reminder] = {}
        self._next = 1
        if path.exists():
            try:
                raw = json.loads(path.read_text())
                for r in raw.get("reminders", []):
                    rem = Reminder(**r)
                    self._items[rem.id] = rem
                self._next = int(raw.get("next_id", len(self._items) + 1))
            except Exception as exc:
                print(f"[reminders] could not read {path}: {exc}; starting fresh.")
                self._items = {}
                self._next = 1

    def add(
        self,
        text: str,
        remind_at: datetime.datetime,
        sensitive: bool | None = None,
    ) -> Reminder:
        with self._lock:
            rid = f"rem_{self._next:03d}"
            self._next += 1
            rem = Reminder(
                id=rid,
                text=text,
                remind_at=remind_at.isoformat(timespec="minutes"),
                sensitive=sensitive,
            )
            self._items[rid] = rem
            self._write()
            return rem

    def due(self, now: datetime.datetime) -> list[Reminder]:
        """Undelivered reminders whose time has arrived, earliest first."""

        with self._lock:
            due = [r for r in self._items.values() if r.is_due(now)]
        return sorted(due, key=lambda r: r.remind_at)

    def pending(self) -> list[Reminder]:
        """All undelivered reminders (due or not), earliest first."""

        with self._lock:
            pend = [r for r in self._items.values() if not r.delivered]
        return sorted(pend, key=lambda r: r.remind_at)

    def mark_delivered(self, rid: str) -> None:
        with self._lock:
            r = self._items.get(rid)
            if r is not None and not r.delivered:
                r.delivered = True
                self._write()

    def all(self) -> list[Reminder]:
        with self._lock:
            return sorted(self._items.values(), key=lambda r: r.remind_at)

    # --- private -------------------------------------------------------------

    def _write(self) -> None:
        """Atomic whole-file write. Caller must hold ``self._lock``."""

        payload = json.dumps(
            {
                "next_id": self._next,
                "reminders": [asdict(r) for r in self._items.values()],
            },
            indent=2,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=self._path.name + ".", suffix=".tmp",
                dir=str(self._path.parent),
            )
            try:
                with os.fdopen(fd, "w") as f:
                    f.write(payload)
                os.replace(tmp_name, self._path)
            except Exception:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
                raise
        except Exception as exc:
            print(f"[reminders] could not write {self._path}: {exc}")
