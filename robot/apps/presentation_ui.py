"""Local presentation console for the privacy-aware reminder prototype.

The console deliberately has two modes:

* ``Guided demo`` is a deterministic, hardware-free walkthrough.  It is useful
  in a thesis presentation because the presenter can advance one decision at a
  time and explain why a sensor was used, skipped, or failed safe.
* ``Live experiment`` launches the existing ``robot.apps.reminder_app`` in a
  child process.  The child remains the source of truth; this module only maps
  its human-readable status lines onto the same visual stages.  The operator
  does not choose a reminder: the console resolves the next approaching pending
  one, counts down to it, and pins the run to it, so what is on screen and what
  the engine acts on are always the same reminder.

No web framework is required.  A small standard-library HTTP server is bound to
the loopback interface, serves the static UI, and exposes a narrow JSON API.
It never loads the camera, microphone, ML models, BLE stack, or Ohbot SDK itself.

Run from the repository root:

    python -m robot.apps.presentation_ui

On macOS, ``Start Thesis UI.command`` provides a double-clickable launcher.
"""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import importlib.util
import json
import mimetypes
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from robot.paths import (
    FACE_DB_PATH,
    FUSION_CONSENT_CACHE_PATH,
    MODELS_DIR,
    OWNER_FACE_PATH,
    OWNER_VOICE_PATH,
    REMINDERS_PATH,
    STATE_DIR,
    VOICE_CONSENT_CACHE_PATH,
    VOICE_DB_PATH,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = PROJECT_ROOT / "robot" / "ui"
MAX_REQUEST_BYTES = 64 * 1024
MAX_EVENTS = 240


STEP_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "id": "configuration",
        "eyebrow": "Study condition",
        "title": "Configure policy",
        "description": "Choose consent memory and the sensing modality.",
    },
    {
        "id": "reminder",
        "eyebrow": "Trigger",
        "title": "Reminder becomes relevant",
        "description": "Load the next pending reminder without opening a sensor.",
    },
    {
        "id": "sensitivity",
        "eyebrow": "Content gate",
        "title": "Check sensitivity",
        "description": "Only sensitive content needs bystander sensing and consent.",
    },
    {
        "id": "owner",
        "eyebrow": "Presence gate",
        "title": "Confirm the owner",
        "description": "The watch link acts as the private owner-presence signal.",
    },
    {
        "id": "microphone",
        "eyebrow": "Sensor 1",
        "title": "Listen for another voice",
        "description": "Analyse the temporary audio window, then discard the recording.",
    },
    {
        "id": "camera",
        "eyebrow": "Sensor 2 · fallback",
        "title": "Scan for a silent bystander",
        "description": "Open the camera only after a microphone miss, then close it.",
    },
    {
        "id": "identity",
        "eyebrow": "Recognition",
        "title": "Resolve a bystander ID",
        "description": "Match an embedding locally; raw audio and video are not retained.",
    },
    {
        "id": "consent",
        "eyebrow": "Private decision",
        "title": "Ask or reuse consent",
        "description": "A Yes/No decision happens on the watch, never on the laptop.",
    },
    {
        "id": "memory",
        "eyebrow": "Policy memory",
        "title": "Store the explicit choice",
        "description": "Remember mode stores answered prompts; re-ask mode stores nothing.",
    },
    {
        "id": "delivery",
        "eyebrow": "Privacy outcome",
        "title": "Deliver the reminder",
        "description": "Speak aloud only when policy permits; otherwise notify the wrist.",
    },
)


SCENARIOS: dict[str, dict[str, str]] = {
    "voice_decline": {
        "title": "Bystander declines disclosure",
        "short": "Voice detected · watch says No",
        "description": "A second voice is recognised. The camera is skipped and the sensitive reminder stays private.",
        "recommended_policy": "remember",
        "recommended_sensors": "both",
        "accent": "coral",
    },
    "camera_consent": {
        "title": "Silent bystander consents",
        "short": "Mic clear · camera sees person · Yes",
        "description": "The mic misses a silent person, so the camera double-check runs. The owner allows disclosure.",
        "recommended_policy": "remember",
        "recommended_sensors": "both",
        "accent": "blue",
    },
    "remembered_decline": {
        "title": "Remembered preference",
        "short": "Recognised person · prompt avoided",
        "description": "The same bystander returns. A saved No is reused, demonstrating the thesis's memory condition.",
        "recommended_policy": "remember",
        "recommended_sensors": "mic",
        "accent": "violet",
    },
    "owner_alone": {
        "title": "Owner is alone",
        "short": "Both sensors clear · speak aloud",
        "description": "Neither sensor finds a bystander, so no consent prompt is needed and the reminder is spoken.",
        "recommended_policy": "remember",
        "recommended_sensors": "both",
        "accent": "green",
    },
    "non_sensitive": {
        "title": "Everyday reminder",
        "short": "Non-sensitive · sensors stay off",
        "description": "A normal errand bypasses all presence sensing and is delivered at its scheduled time.",
        "recommended_policy": "reask",
        "recommended_sensors": "both",
        "accent": "gold",
    },
    "camera_failure": {
        "title": "Fail-safe sensor error",
        "short": "Camera inconclusive · private fallback",
        "description": "The mic is clear but the fallback scan fails. The system never interprets failure as 'alone'.",
        "recommended_policy": "remember",
        "recommended_sensors": "both",
        "accent": "red",
    },
}


def _fresh_steps() -> list[dict[str, Any]]:
    return [
        {
            **definition,
            "status": "pending",
            "detail": definition["description"],
        }
        for definition in STEP_DEFINITIONS
    ]


def _iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _validate_config(payload: dict[str, Any], *, live: bool = False) -> dict[str, Any]:
    policy = str(payload.get("policy", "remember"))
    sensors = str(payload.get("sensors", "both"))
    if policy not in {"remember", "reask"}:
        raise ValueError("policy must be 'remember' or 'reask'")
    if sensors not in {"mic", "both"}:
        raise ValueError("sensors must be 'mic' or 'both'")

    result: dict[str, Any] = {"policy": policy, "sensors": sensors}
    if live:
        try:
            lead = float(payload.get("monitor_lead", 420))
            listen = float(payload.get("listen_duration", 300))
        except (TypeError, ValueError) as exc:
            raise ValueError("timing values must be numbers") from exc
        if not (0 < listen <= lead <= 86_400):
            raise ValueError("timing must satisfy 0 < listen duration <= monitor lead <= 24 hours")
        laptop_voice = payload.get("laptop_voice", True)
        if not isinstance(laptop_voice, bool):
            raise ValueError("laptop_voice must be true or false")
        # The target reminder is NOT a client choice: start_live resolves it from
        # the pending queue so the run always follows the countdown on screen.
        result.update(
            monitor_lead=lead,
            listen_duration=listen,
            laptop_voice=laptop_voice,
        )
    return result


def _json_record_count(path: Path, keys: tuple[str, ...]) -> int:
    """Best-effort count for local setup cards; malformed state is reported as 0."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    for key in keys:
        value = raw.get(key) if isinstance(raw, dict) else None
        if isinstance(value, (dict, list)):
            return len(value)
    return len(raw) if isinstance(raw, (dict, list)) else 0


def _pending_entry(item: dict[str, Any]) -> dict[str, Any]:
    """One pending reminder, plus how many seconds remain until it is due.

    ``seconds_until`` is computed here rather than in the browser so the
    countdown uses the same clock and the same naive local timestamps as the
    engine's own due check; a negative value means the reminder is overdue and
    the engine will act on it as soon as a run starts.
    """

    raw = str(item.get("remind_at", ""))
    try:
        seconds: float | None = (dt.datetime.fromisoformat(raw) - dt.datetime.now()).total_seconds()
    except ValueError:
        seconds = None
    return {
        "id": str(item.get("id", "")),
        "text": str(item.get("text", "")),
        "remind_at": raw,
        "sensitive": item.get("sensitive"),
        "seconds_until": seconds,
    }


def _is_upcoming(entry: dict[str, Any]) -> bool:
    """True when a pending reminder still lies ahead and can be counted down to."""

    seconds = entry.get("seconds_until")
    return seconds is not None and seconds > 0


def readiness_snapshot() -> dict[str, Any]:
    """Return fast, side-effect-free local preparation checks."""

    pending: list[dict[str, Any]] = []
    try:
        raw = json.loads(REMINDERS_PATH.read_text(encoding="utf-8"))
        reminders = raw.get("reminders", []) if isinstance(raw, dict) else []
        pending = [r for r in reminders if isinstance(r, dict) and not r.get("delivered")]
        pending.sort(key=lambda item: str(item.get("remind_at", "")))
    except (OSError, ValueError):
        pass
    # The console never asks which reminder to run: it resolves the next
    # approaching one itself and counts down to it, so the countdown and the run
    # cannot disagree. A reminder whose time already passed cannot be counted
    # down to, so undelivered leftovers are stepped over in favour of the next
    # real one; if every pending reminder is stale the soonest is still offered,
    # otherwise the console would refuse to start at all.
    queue = [_pending_entry(item) for item in pending]
    upcoming = [item for item in queue if _is_upcoming(item)]
    overdue = [item for item in queue if not _is_upcoming(item)]
    next_reminder = upcoming[0] if upcoming else (queue[0] if queue else None)

    model_count = sum(1 for path in MODELS_DIR.glob("*.onnx") if path.is_file())
    dependencies = {
        name: importlib.util.find_spec(module) is not None
        for name, module in {
            "OpenCV": "cv2",
            "SoundDevice": "sounddevice",
            "Whisper": "whisper",
            "BLE": "bleak",
            "Ohbot SDK": "ohbot",
            "Resemblyzer": "resemblyzer",
        }.items()
    }
    return {
        "python": {
            "ready": sys.version_info[:2] == (3, 13),
            "label": f"Python {sys.version_info.major}.{sys.version_info.minor}",
            "detail": "3.13 is the tested interpreter" if sys.version_info[:2] == (3, 13)
            else "Python 3.13 is recommended for the hardware dependencies",
        },
        "voice": {
            "ready": OWNER_VOICE_PATH.exists(),
            "label": "Voice enrollment",
            "detail": "Owner voiceprint found" if OWNER_VOICE_PATH.exists()
            else "Run: python -m robot.apps.enroll_voice",
        },
        "face": {
            "ready": OWNER_FACE_PATH.exists(),
            "label": "Face enrollment",
            "detail": "Owner faceprint found" if OWNER_FACE_PATH.exists()
            else "Run: python -m robot.apps.enroll_face",
        },
        "models": {
            "ready": model_count >= 2,
            "label": "Face models",
            "detail": f"{model_count}/2 local ONNX models available",
        },
        "reminders": {
            "ready": bool(upcoming),
            "label": "Pending reminder",
            "detail": f"next {next_reminder['text']!r} at {next_reminder['remind_at'][11:19]}"
                      + (f"; {len(overdue)} overdue leftover(s) ignored" if overdue else "")
            if next_reminder else "Run: python -m robot.apps.add_reminder",
        },
        "watch": {
            "ready": None,
            "label": "Bangle.js watch",
            "detail": "Connection is checked only when Live experiment starts",
        },
        "microphone": {
            "ready": dependencies["SoundDevice"],
            "label": "Laptop microphone",
            "detail": "Driver available; use Test microphone to open it"
            if dependencies["SoundDevice"] else "sounddevice/PortAudio is unavailable",
        },
        "camera": {
            "ready": dependencies["OpenCV"],
            "label": "Robot camera",
            "detail": "OpenCV available; use Test camera to verify the external view"
            if dependencies["OpenCV"] else "OpenCV is unavailable",
        },
        "ohbot": {
            "ready": dependencies["Ohbot SDK"],
            "label": "Ohbot",
            "detail": "SDK installed; use Test Ohbot with the robot connected"
            if dependencies["Ohbot SDK"] else "Ohbot SDK is unavailable",
        },
        "dependencies": dependencies,
        "next_reminder": next_reminder,
        "upcoming_count": len(upcoming),
        "overdue_count": len(overdue),
        "pending_reminders": queue[:5],
        "local_records": {
            "voice_gallery": _json_record_count(VOICE_DB_PATH, ("people", "records")),
            "face_gallery": _json_record_count(FACE_DB_PATH, ("people", "records")),
            "voice_consent": _json_record_count(VOICE_CONSENT_CACHE_PATH, ("decisions", "records")),
            "fusion_consent": _json_record_count(FUSION_CONSENT_CACHE_PATH, ("decisions", "records")),
        },
    }


ALGORITHM_CATALOG: tuple[dict[str, Any], ...] = (
    {"name": "RMS + peak gate", "modality": "Voice", "stage": "Sound gate",
     "role": "Reject quiet windows cheaply", "threshold": "RMS 0.020; peak 0.035; 6% voiced"},
    {"name": "Silero VAD", "modality": "Voice", "stage": "Speech gate",
     "role": "Reject appliances and non-speech noise", "threshold": "≥ configured human-speech duration"},
    {"name": "Resemblyzer GE2E", "modality": "Voice", "stage": "Speaker identity",
     "role": "Owner subtraction and anonymous bystander matching", "embedding_dim": 256,
     "threshold": "owner ≥ 0.73; bystander re-ID ≥ 0.70 cosine"},
    {"name": "YuNet", "modality": "Camera", "stage": "Face detection",
     "role": "Locate faces during each robot-head view", "threshold": "confidence ≥ 0.90"},
    {"name": "SFace", "modality": "Camera", "stage": "Face identity",
     "role": "Owner subtraction and anonymous bystander matching", "embedding_dim": 128,
     "threshold": "owner ≥ 0.50; bystander re-ID ≥ 0.363 cosine"},
    {"name": "Consent memory", "modality": "Policy", "stage": "Disclosure decision",
     "role": "Remember stores answered Yes/No choices per anonymous ID; re-ask stores nothing",
     "threshold": "No answer or sensor uncertainty → private delivery"},
)


def _read_benchmark_csv(path: Path, source: str) -> list[dict[str, Any]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except OSError:
        return []
    numeric = {
        "init_ms", "lat_median_ms", "lat_p95_ms", "lat_mean_ms", "fps", "rtf",
        "peak_rss_mb", "model_size_mb", "embedding_dim",
    }
    result: list[dict[str, Any]] = []
    for row in rows:
        clean: dict[str, Any] = {**row, "source": source, "file": str(path)}
        clean["ok"] = str(row.get("ok", "")).lower() == "true"
        for key in numeric:
            raw = row.get(key, "")
            try:
                clean[key] = float(raw) if raw not in {"", None} else None
            except (TypeError, ValueError):
                clean[key] = None
        clean["accuracy_value"] = None
        clean["accuracy_label"] = str(row.get("accuracy", "") or "")
        raw_accuracy = row.get("accuracy")
        if raw_accuracy:
            try:
                accuracy = json.loads(raw_accuracy)
            except (TypeError, json.JSONDecodeError):
                accuracy = None
            if isinstance(accuracy, dict):
                detection_rate = accuracy.get("detection_rate")
                eer = accuracy.get("eer")
                if isinstance(detection_rate, (int, float)):
                    clean["accuracy_value"] = 100.0 * float(detection_rate)
                    clean["accuracy_label"] = f"Detection {clean['accuracy_value']:.1f}%"
                elif isinstance(eer, (int, float)):
                    clean["accuracy_value"] = 100.0 * (1.0 - float(eer))
                    clean["accuracy_label"] = (
                        f"1−EER {clean['accuracy_value']:.1f}% "
                        f"(EER {100.0 * float(eer):.1f}%)"
                    )
                elif accuracy.get("note"):
                    clean["accuracy_label"] = str(accuracy["note"])
        result.append(clean)
    return result


def benchmark_snapshot() -> dict[str, Any]:
    base = PROJECT_ROOT / "robot" / "bench" / "results"
    runs_root = STATE_DIR / "benchmark_runs"
    datasets: list[dict[str, Any]] = []
    for modality in ("camera", "voice"):
        path = base / f"{modality}_results.csv"
        datasets.append({
            "id": f"bundled-{modality}", "modality": modality, "source": "Bundled baseline",
            "created_at": dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
            if path.exists() else None,
            "rows": _read_benchmark_csv(path, "Bundled baseline"),
        })
    if runs_root.exists():
        for path in sorted(runs_root.glob("*/*_results.csv"), reverse=True)[:12]:
            modality = "camera" if path.name.startswith("camera") else "voice"
            datasets.append({
                "id": path.parent.name + "-" + modality,
                "modality": modality,
                "source": f"Local run {path.parent.name}",
                "created_at": dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "rows": _read_benchmark_csv(path, f"Local run {path.parent.name}"),
            })
    return {"catalog": ALGORITHM_CATALOG, "datasets": datasets}


def evaluation_snapshot() -> dict[str, Any]:
    root = PROJECT_ROOT / "robot" / "bench" / "eval_data"
    summary: dict[str, Any] = {"root": str(root), "faces": {}, "voices": {}}
    for modality, suffix in (("faces", ".jpg"), ("voices", ".wav")):
        folder = root / modality
        people: dict[str, Any] = {}
        if folder.exists():
            for person in sorted(p for p in folder.iterdir() if p.is_dir()):
                files = list(person.glob(f"*{suffix}"))
                conditions = sorted({f.stem.rsplit("_", 1)[0] for f in files})
                people[person.name] = {"samples": len(files), "conditions": conditions}
        summary[modality] = people
    named_people = [p for p in summary["faces"] if p != "_negative"]
    voice_people = list(summary["voices"])
    all_conditions = {
        c for modality in ("faces", "voices")
        for data in summary[modality].values() for c in data["conditions"]
    }
    summary["coverage"] = {
        "people": max(len(named_people), len(voice_people)),
        "conditions": len(all_conditions),
        "minimum_samples_met": all(
            data["samples"] >= 4
            for modality in ("faces", "voices")
            for name, data in summary[modality].items() if name != "_negative"
        ) if named_people or voice_people else False,
        "recommended": "≥3 people, ≥2 conditions, ≥4 samples each",
    }
    return summary


def _update(step: str, status: str, detail: str) -> dict[str, str]:
    return {"step": step, "status": status, "detail": detail}


def _base_timeline(config: dict[str, Any], *, sensitive: bool = True) -> list[dict[str, Any]]:
    policy_label = "Remember explicit answers" if config["policy"] == "remember" else "Ask every time"
    sensor_label = "microphone → camera fallback" if config["sensors"] == "both" else "microphone only"
    return [
        {
            "updates": [
                _update("configuration", "complete", f"{policy_label}; {sensor_label}."),
                _update("reminder", "active", "Reading the next pending reminder from local state."),
            ],
            "event": f"Condition locked: {config['policy']} × {config['sensors']}",
            "tone": "info",
        },
        {
            "updates": [
                _update("reminder", "complete", "Reminder rem_demo is due: ‘doctor's appointment at 15:00’."),
                _update("sensitivity", "active", "Classifying content before activating any room sensor."),
            ],
            "event": "A scheduled reminder entered the privacy pipeline",
            "tone": "info",
        },
        {
            "updates": [
                _update(
                    "sensitivity",
                    "complete",
                    "Sensitive health information — presence gating is required."
                    if sensitive else "Everyday content — presence gating is not required.",
                ),
                _update("owner", "active", "Checking the private BLE owner-presence signal."),
            ],
            "event": "Sensitive content detected" if sensitive else "Reminder classified as non-sensitive",
            "tone": "warning" if sensitive else "success",
        },
        {
            "updates": [
                _update("owner", "complete", "Watch connected — the owner is in the room."),
            ],
            "event": "Owner presence confirmed through the watch link",
            "tone": "success",
        },
    ]


def build_demo_timeline(scenario: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Build ordered presenter-controlled actions for one demonstration path."""

    if scenario not in SCENARIOS:
        raise ValueError("unknown demo scenario")
    if scenario in {"camera_consent", "camera_failure"} and config["sensors"] != "both":
        raise ValueError("this scenario needs the ‘microphone + camera’ sensor setting")
    if scenario == "remembered_decline" and config["policy"] != "remember":
        raise ValueError("the remembered-preference scenario needs the ‘remember’ policy")

    sensitive = scenario != "non_sensitive"
    actions = _base_timeline(config, sensitive=sensitive)

    if scenario == "non_sensitive":
        actions.extend(
            [
                {
                    "updates": [
                        _update("microphone", "skipped", "Not needed for non-sensitive content."),
                        _update("camera", "skipped", "Not needed for non-sensitive content."),
                        _update("identity", "skipped", "No bystander recognition needed."),
                        _update("consent", "skipped", "No disclosure decision needed."),
                        _update("delivery", "active", "Preparing normal spoken delivery."),
                        _update("memory", "skipped", "No consent decision was requested."),
                    ],
                    "event": "All presence and consent stages bypassed",
                    "tone": "success",
                },
                {
                    "updates": [_update("delivery", "complete", "Spoken aloud: ‘Here is your reminder to buy milk.’")],
                    "event": "Everyday reminder delivered without activating a sensor",
                    "tone": "success",
                },
            ]
        )
        return actions

    actions.append(
        {
            "updates": [_update("microphone", "active", "Listening during the bounded pre-reminder window…")],
            "event": "Microphone opened — raw audio exists only for this analysis window",
            "tone": "sensor",
        }
    )

    if scenario in {"camera_consent", "camera_failure", "owner_alone"}:
        if config["sensors"] == "both":
            actions.append(
                {
                    "updates": [
                        _update("microphone", "complete", "No non-owner voice detected; temporary audio discarded."),
                        _update("camera", "active", "Mic was clear. Opening the camera for a brief head scan…"),
                    ],
                    "event": "Mic miss escalated to the camera fallback",
                    "tone": "sensor",
                }
            )
        else:
            actions.append(
                {
                    "updates": [
                        _update("microphone", "complete", "No audible bystander; temporary audio discarded."),
                        _update("camera", "skipped", "Mic-only condition — camera is never accessed."),
                        _update("identity", "skipped", "No bystander voice to identify."),
                        _update("consent", "skipped", "No audible bystander, so no watch prompt."),
                        _update("delivery", "active", "Voice-only condition treats the room as clear."),
                        _update("memory", "skipped", "No consent decision was requested."),
                    ],
                    "event": "Voice-only condition found no audible bystander",
                    "tone": "info",
                }
            )
            actions.append(
                {
                    "updates": [_update("delivery", "complete", "Owner treated as alone; reminder spoken aloud.")],
                    "event": "Sensitive reminder delivered aloud",
                    "tone": "success",
                }
            )
            return actions

    if scenario == "camera_failure":
        actions.extend(
            [
                {
                    "updates": [
                        _update("camera", "warning", "No usable camera frame — presence is inconclusive."),
                        _update("identity", "skipped", "No reliable frame to identify."),
                        _update("consent", "skipped", "The system cannot safely frame a bystander consent question."),
                        _update("delivery", "active", "Applying the unified app's privacy-safe fallback."),
                        _update("memory", "skipped", "No explicit answer was received."),
                    ],
                    "event": "Sensor failure was not interpreted as ‘owner alone’",
                    "tone": "warning",
                },
                {
                    "updates": [_update("delivery", "complete", "Reminder withheld aloud and sent privately to the wrist.")],
                    "event": "Fail-safe outcome: private watch delivery",
                    "tone": "private",
                },
            ]
        )
        return actions

    if scenario == "owner_alone":
        actions.extend(
            [
                {
                    "updates": [
                        _update("camera", "complete", "Head scan saw no bystander; camera closed and head re-centred."),
                        _update("identity", "skipped", "There is no bystander to identify."),
                        _update("consent", "skipped", "The owner is alone, so consent is unnecessary."),
                        _update("delivery", "active", "Both presence checks agree that the owner is alone."),
                        _update("memory", "skipped", "No consent decision was requested."),
                    ],
                    "event": "Independent sensor checks found no bystander",
                    "tone": "success",
                },
                {
                    "updates": [_update("delivery", "complete", "Sensitive reminder spoken aloud to the owner.")],
                    "event": "Owner-alone delivery completed",
                    "tone": "success",
                },
            ]
        )
        return actions

    if scenario == "camera_consent":
        actions.extend(
            [
                {
                    "updates": [
                        _update("camera", "complete", "Silent bystander found; camera closed and head re-centred."),
                        _update("identity", "active", "Comparing the local face embedding with the gallery."),
                    ],
                    "event": "Camera caught the microphone's blind spot: a silent person",
                    "tone": "sensor",
                },
                {
                    "updates": [
                        _update("identity", "complete", "Recognised locally as face:person_001."),
                        _update("consent", "active", "No stored answer yet — asking privately on the watch."),
                    ],
                    "event": "Stable bystander identity resolved without retaining video",
                    "tone": "info",
                },
                {
                    "updates": [
                        _update("consent", "complete", "Owner tapped Yes on the watch."),
                        _update(
                            "memory", "active" if config["policy"] == "remember" else "skipped",
                            "Saving the explicit Yes for this bystander."
                            if config["policy"] == "remember" else "Re-ask policy stores no decision.",
                        ),
                    ],
                    "event": "Watch response: YES",
                    "tone": "success",
                },
                {
                    "updates": [
                        _update(
                            "memory",
                            "complete" if config["policy"] == "remember" else "skipped",
                            "Explicit Yes stored under the bystander's local ID."
                            if config["policy"] == "remember" else "Re-ask policy stores no decision.",
                        ),
                        _update("delivery", "active", "Explicit consent permits spoken disclosure."),
                    ],
                    "event": "Consent memory resolved before delivery",
                    "tone": "info",
                },
                {
                    "updates": [_update("delivery", "complete", "Sensitive reminder spoken aloud with consent.")],
                    "event": "Consented reminder delivered aloud",
                    "tone": "success",
                },
            ]
        )
    else:
        # voice_decline and remembered_decline share the mic/identity path.
        actions.extend(
            [
                {
                    "updates": [
                        _update("microphone", "complete", "Non-owner speech detected; temporary audio discarded."),
                        _update("camera", "skipped", "Mic already found a bystander — camera remains closed."),
                        _update("identity", "active", "Comparing the local voice embedding with the gallery."),
                    ],
                    "event": "A bystander voice was isolated from the owner's voiceprint",
                    "tone": "sensor",
                },
                {
                    "updates": [
                        _update("identity", "complete", "Recognised locally as voice:person_001."),
                        _update(
                            "consent",
                            "active",
                            "Looking up this person's stored disclosure preference."
                            if scenario == "remembered_decline" else "No stored answer yet — asking privately on the watch.",
                        ),
                    ],
                    "event": "Bystander identity resolved without retaining raw audio",
                    "tone": "info",
                },
                {
                    "updates": [
                        _update(
                            "consent",
                            "complete",
                            "Remembered No reused — the watch prompt is intentionally skipped."
                            if scenario == "remembered_decline" else "Owner tapped No on the watch.",
                        ),
                        _update(
                            "memory",
                            "complete" if scenario == "remembered_decline" else (
                                "active" if config["policy"] == "remember" else "skipped"
                            ),
                            "Existing explicit No remains in the local consent cache."
                            if scenario == "remembered_decline" else (
                                "Saving the explicit No for this bystander."
                                if config["policy"] == "remember" else "Re-ask policy stores no decision."
                            ),
                        ),
                    ],
                    "event": "Saved preference reused: NO"
                    if scenario == "remembered_decline" else "Watch response: NO",
                    "tone": "private",
                },
                {
                    "updates": [
                        _update(
                            "memory",
                            "complete" if scenario == "remembered_decline" else (
                                "complete" if config["policy"] == "remember" else "skipped"
                            ),
                            "Existing explicit No remains in the local consent cache."
                            if scenario == "remembered_decline" else (
                                "Explicit No stored under the bystander's local ID."
                                if config["policy"] == "remember" else "Re-ask policy stores no decision."
                            ),
                        ),
                        _update("delivery", "active", "Disclosure is not permitted in front of this bystander."),
                    ],
                    "event": "Consent memory resolved before delivery",
                    "tone": "info",
                },
                {
                    "updates": [_update("delivery", "complete", "Robot stays neutral; reminder sent privately to the wrist.")],
                    "event": "Private wrist delivery completed",
                    "tone": "private",
                },
            ]
        )
    return actions


class PresentationController:
    """Thread-safe state machine shared by HTTP request and process threads."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._timeline: list[dict[str, Any]] = []
        self._cursor = 0
        self._event_seq = 0
        self._base_url = ""
        self._telemetry_token = secrets.token_urlsafe(24)
        self._frame: bytes | None = None
        self._frame_version = 0
        self._state: dict[str, Any] = {}
        self.reset()

    def configure_transport(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def reset(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("stop the live experiment before resetting")
            self._timeline = []
            self._cursor = 0
            self._state = {
                "mode": "idle",
                "status": "idle",
                "scenario": None,
                "config": {"policy": "remember", "sensors": "both"},
                "steps": _fresh_steps(),
                "events": [],
                "current_step": None,
                "started_at": None,
                "headline": "Ready for a guided walkthrough or live experiment",
                "outcome": None,
                "version": 1,
                "demo": {"cursor": 0, "total": 0, "has_next": False},
                "sensors": {"microphone": False, "camera": False},
                "metrics": {"microphone_level": 0.0, "head_position": "centred"},
                "frame_version": self._frame_version,
                "identity": None,
                "job": {"kind": None, "status": "idle", "progress": None, "result": None},
                "reminder_draft": None,
            }
            self._frame = None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = copy.deepcopy(self._state)
            state["process_running"] = bool(self._process and self._process.poll() is None)
            state["frame_available"] = self._frame is not None
        state["readiness"] = readiness_snapshot()
        return state

    def frame_snapshot(self) -> tuple[bytes | None, int]:
        with self._lock:
            return self._frame, self._frame_version

    def _touch(self) -> None:
        self._state["version"] += 1

    def _event(self, message: str, tone: str = "info", *, source: str = "system") -> None:
        self._event_seq += 1
        self._state["events"].append(
            {
                "id": self._event_seq,
                "at": dt.datetime.now().astimezone().strftime("%H:%M:%S"),
                "message": message,
                "tone": tone,
                "source": source,
            }
        )
        self._state["events"] = self._state["events"][-MAX_EVENTS:]

    def _set_step(self, step_id: str, status: str, detail: str) -> None:
        allowed = {"pending", "active", "complete", "skipped", "warning", "error"}
        if status not in allowed:
            raise ValueError(f"unknown step status: {status}")
        for step in self._state["steps"]:
            if step["id"] == step_id:
                step["status"] = status
                step["detail"] = detail
                if status == "active":
                    self._state["current_step"] = step_id
                    self._state["headline"] = step["title"]
                return
        raise ValueError(f"unknown step: {step_id}")

    def start_demo(self, scenario: str, raw_config: dict[str, Any]) -> None:
        config = _validate_config(raw_config)
        timeline = build_demo_timeline(scenario, config)
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("a live experiment is already running")
            self._timeline = timeline
            self._cursor = 0
            self._state.update(
                mode="demo",
                status="ready",
                scenario=scenario,
                config=config,
                steps=_fresh_steps(),
                events=[],
                current_step="configuration",
                started_at=_iso_now(),
                headline="Configure policy",
                outcome=None,
                demo={"cursor": 0, "total": len(timeline), "has_next": True},
            )
            self._set_step(
                "configuration",
                "active",
                "The presenter controls each transition. Press Next step to begin.",
            )
            self._event(f"Guided demo loaded: {SCENARIOS[scenario]['title']}", "info", source="demo")
            self._touch()

    def advance_demo(self) -> None:
        with self._lock:
            if self._state["mode"] != "demo":
                raise RuntimeError("start a guided demo first")
            if self._cursor >= len(self._timeline):
                return
            action = self._timeline[self._cursor]
            for update in action["updates"]:
                self._set_step(update["step"], update["status"], update["detail"])
            self._event(action["event"], action.get("tone", "info"), source="demo")
            self._cursor += 1
            has_next = self._cursor < len(self._timeline)
            self._state["demo"] = {
                "cursor": self._cursor,
                "total": len(self._timeline),
                "has_next": has_next,
            }
            self._state["status"] = "running" if has_next else "complete"
            if not has_next:
                self._state["current_step"] = "delivery"
                self._state["headline"] = "Walkthrough complete"
                delivery = next(step for step in self._state["steps"] if step["id"] == "delivery")
                self._state["outcome"] = delivery["detail"]
                self._event("End of guided path — ready for questions or another scenario", "success", source="demo")
            self._touch()

    def previous_demo(self) -> None:
        """Move one presenter-controlled action back by replaying from the start."""

        with self._lock:
            if self._state["mode"] != "demo":
                raise RuntimeError("start a guided demo first")
            target = max(0, self._cursor - 1)
            scenario = str(self._state["scenario"])
            config = dict(self._state["config"])
            self._cursor = 0
            self._state.update(
                status="ready", steps=_fresh_steps(), events=[], outcome=None,
                current_step="configuration", headline="Configure policy",
            )
            self._set_step(
                "configuration", "active",
                "The presenter controls each transition. Press Next step to begin.",
            )
            self._event(f"Guided demo loaded: {SCENARIOS[scenario]['title']}", "info", source="demo")
            while self._cursor < target:
                action = self._timeline[self._cursor]
                for update in action["updates"]:
                    self._set_step(update["step"], update["status"], update["detail"])
                self._event(action["event"], action.get("tone", "info"), source="demo")
                self._cursor += 1
            self._state["demo"] = {
                "cursor": self._cursor,
                "total": len(self._timeline),
                "has_next": self._cursor < len(self._timeline),
            }
            self._state["config"] = config
            self._touch()

    def start_live(self, raw_config: dict[str, Any]) -> None:
        config = _validate_config(raw_config, live=True)
        readiness = readiness_snapshot()
        target = readiness.get("next_reminder")
        if not target:
            raise ValueError(
                "no pending reminder to run; add one in the Reminders tab first"
            )
        config["reminder_id"] = target["id"]
        config["reminder"] = target
        if not readiness["voice"]["ready"]:
            raise RuntimeError("voice enrollment is missing; run python -m robot.apps.enroll_voice")
        if config["sensors"] == "both" and not readiness["face"]["ready"]:
            raise RuntimeError("face enrollment is missing; run python -m robot.apps.enroll_face")

        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("a live experiment is already running")

            command = [
                sys.executable,
                "-u",
                "-m",
                "robot.apps.reminder_app",
                "--policy",
                config["policy"],
                "--sensors",
                config["sensors"],
                "--monitor-lead",
                f"{config['monitor_lead']:g}",
                "--listen-duration",
                f"{config['listen_duration']:g}",
                # Pin the run to the reminder the console is counting down to;
                # without it the engine would also pick up every other pending
                # reminder that falls due while this one is being handled.
                "--reminder-id",
                config["reminder_id"],
            ]
            env = os.environ.copy()
            env["THESIS_UI_URL"] = self._base_url
            env["THESIS_UI_TOKEN"] = self._telemetry_token
            # The browser is the only preview surface during a presentation.
            env["CAMERA_PREVIEW"] = "0"
            if config["laptop_voice"]:
                env["NO_OHBOT"] = "1"
            else:
                env.pop("NO_OHBOT", None)

            self._state.update(
                mode="live",
                status="starting",
                scenario=None,
                config=config,
                steps=_fresh_steps(),
                events=[],
                current_step="configuration",
                started_at=_iso_now(),
                headline=f"Waiting for {target['text']!r} at {target['remind_at'][11:19]}",
                outcome=None,
                demo={"cursor": 0, "total": 0, "has_next": False},
                sensors={"microphone": False, "camera": False},
                metrics={"microphone_level": 0.0, "head_position": "centred"},
                identity=None,
                job={"kind": "live", "status": "running", "progress": None, "result": None},
            )
            self._frame = None
            self._set_step(
                "configuration", "active",
                f"Starting reminder_app for the next reminder: {target['id']} "
                f"({target['text']!r}, due {target['remind_at'][11:19]}).",
            )
            self._event(
                f"Live experiment requested for {target['id']} ({target['text']!r})",
                "info", source="live",
            )

            try:
                self._process = subprocess.Popen(
                    command,
                    cwd=PROJECT_ROOT,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    start_new_session=os.name != "nt",
                )
            except OSError as exc:
                self._state["status"] = "error"
                self._set_step("configuration", "error", f"Could not start: {exc}")
                self._event(f"Launch failed: {exc}", "error", source="live")
                self._touch()
                raise RuntimeError(f"could not launch the live pipeline: {exc}") from exc
            process = self._process
            self._state["status"] = "running"
            self._touch()

        threading.Thread(
            target=self._read_process,
            args=(process,),
            daemon=True,
            name="presentation-live-output",
        ).start()

    def save_reminder(self, payload: dict[str, Any]) -> dict[str, Any]:
        text_value = str(payload.get("text", "")).strip()
        if not 1 <= len(text_value) <= 300:
            raise ValueError("reminder text must contain 1–300 characters")
        raw_when = str(payload.get("remind_at", "")).strip()
        try:
            when = dt.datetime.fromisoformat(raw_when)
        except ValueError as exc:
            raise ValueError("remind_at must be a valid local ISO date/time") from exc
        if when <= dt.datetime.now() + dt.timedelta(seconds=3):
            raise ValueError("reminder time must be in the future")
        sensitive = payload.get("sensitive")
        if not isinstance(sensitive, bool):
            raise ValueError("sensitive must be true or false")
        from robot.core.reminders import ReminderStore

        reminder = ReminderStore(REMINDERS_PATH).add(
            text_value, when, sensitive=sensitive, timespec="seconds",
        )
        with self._lock:
            self._event(f"Reminder {reminder.id} saved for {reminder.remind_at}", "success", source="setup")
            self._touch()
        return {
            "id": reminder.id, "text": reminder.text,
            "remind_at": reminder.remind_at, "sensitive": reminder.sensitive,
        }

    def start_job(self, kind: str, payload: dict[str, Any]) -> None:
        """Launch one setup, evaluation, device-test, or benchmark worker."""

        allowed = {
            "face_enrollment", "voice_enrollment", "voice_reminder",
            "device_camera", "device_microphone", "device_watch", "device_ohbot",
            "eval_face", "eval_voice", "benchmark_camera", "benchmark_voice",
        }
        if kind not in allowed:
            raise ValueError("unknown job kind")
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("another hardware or benchmark job is already running")

        env = os.environ.copy()
        env["THESIS_UI_URL"] = self._base_url
        env["THESIS_UI_TOKEN"] = self._telemetry_token
        env["THESIS_UI_JOB"] = "1"
        command: list[str]
        if kind in {"face_enrollment", "voice_enrollment", "voice_reminder"}:
            module = {
                "face_enrollment": "robot.apps.enroll_face",
                "voice_enrollment": "robot.apps.enroll_voice",
                "voice_reminder": "robot.apps.add_reminder",
            }[kind]
            command = [sys.executable, "-u", "-m", module]
            overwrite = payload.get("overwrite", False)
            if not isinstance(overwrite, bool):
                raise ValueError("overwrite must be true or false")
            if overwrite:
                env["THESIS_UI_OVERWRITE"] = "1"
            if kind == "voice_reminder":
                seconds = float(payload.get("seconds", 8))
                model = str(payload.get("model", "base.en"))
                if not 2 <= seconds <= 30:
                    raise ValueError("voice recording duration must be 2–30 seconds")
                if model not in {"tiny.en", "base.en", "small.en"}:
                    raise ValueError("unsupported Whisper model")
                command.extend(["--seconds", f"{seconds:g}", "--model", model])
        elif kind.startswith("device_") or kind.startswith("eval_"):
            worker_kind = kind.replace("device_", "device-").replace("eval_", "eval-")
            command = [sys.executable, "-u", "-m", "robot.apps.presentation_worker", worker_kind]
            if kind == "device_ohbot":
                env.pop("NO_OHBOT", None)
            if kind == "eval_face":
                label = str(payload.get("label", "")).strip()
                condition = str(payload.get("condition", "default")).strip()
                negative = payload.get("negative", False)
                if not isinstance(negative, bool):
                    raise ValueError("negative must be true or false")
                shots = int(payload.get("shots", 5))
                if not negative and not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", label):
                    raise ValueError("face label must use letters, numbers, '_' or '-'")
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", condition):
                    raise ValueError("condition must use letters, numbers, '_' or '-'")
                if not 1 <= shots <= 100:
                    raise ValueError("shots must be between 1 and 100")
                command.extend(["--label", label or "_negative", "--condition", condition,
                                "--count", str(shots)])
                if negative:
                    command.append("--negative")
            elif kind == "eval_voice":
                label = str(payload.get("label", "")).strip()
                condition = str(payload.get("condition", "default")).strip()
                clips = int(payload.get("clips", 3))
                seconds = float(payload.get("seconds", 4))
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", label):
                    raise ValueError("speaker label must use letters, numbers, '_' or '-'")
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", condition):
                    raise ValueError("condition must use letters, numbers, '_' or '-'")
                if not 1 <= clips <= 30 or not 1 <= seconds <= 30:
                    raise ValueError("voice capture limits are 1–30 clips of 1–30 seconds")
                command.extend(["--label", label, "--condition", condition,
                                "--count", str(clips), "--seconds", f"{seconds:g}"])
        else:
            modality = kind.split("_", 1)[1]
            candidates = str(payload.get("candidates", "")).strip()
            repeats = int(payload.get("repeats", 50 if modality == "camera" else 200))
            timeout = float(payload.get("timeout", 900 if modality == "camera" else 600))
            permitted = {
                "camera": {"haar", "yunet", "opencv_dnn_ssd", "mediapipe", "hog_people", "scrfd", "sface", "arcface"},
                "voice": {"rms", "webrtc", "silero", "resemblyzer", "ecapa", "xvector"},
            }[modality]
            chosen = [item.strip() for item in candidates.split(",") if item.strip()]
            if chosen and not set(chosen) <= permitted:
                raise ValueError("one or more benchmark candidates are unknown")
            if not 1 <= repeats <= 5000 or not 10 <= timeout <= 3600:
                raise ValueError("benchmark repeats/timeout are outside safe limits")
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = STATE_DIR / "benchmark_runs" / stamp
            script = PROJECT_ROOT / "robot" / "bench" / f"bench_{modality}.py"
            command = [sys.executable, "-u", str(script), "--repeats", str(repeats),
                       "--timeout", f"{timeout:g}", "--out-dir", str(out_dir)]
            if chosen:
                command.extend(["--only", ",".join(chosen)])
            if modality == "camera":
                resolution = str(payload.get("resolution", "640x480"))
                if not re.fullmatch(r"[0-9]{2,5}x[0-9]{2,5}", resolution):
                    raise ValueError("resolution must look like 640x480")
                command.extend(["--res", resolution])
            use_eval_data = payload.get("use_eval_data", False)
            if not isinstance(use_eval_data, bool):
                raise ValueError("use_eval_data must be true or false")
            if use_eval_data:
                command.extend(["--data", str(PROJECT_ROOT / "robot" / "bench" / "eval_data")])

        with self._lock:
            # Validation above can take long enough for another request thread
            # to claim the single hardware lane, so enforce the invariant again
            # immediately before spawning.
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("another hardware or benchmark job is already running")
            self._state.update(
                mode="job", status="starting", headline=f"Running {kind.replace('_', ' ')}",
                job={"kind": kind, "status": "starting", "progress": 0.0, "result": None},
                reminder_draft=None,
            )
            self._event(f"Started {kind.replace('_', ' ')}", "info", source="job")
            try:
                self._process = subprocess.Popen(
                    command, cwd=PROJECT_ROOT, env=env,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    start_new_session=os.name != "nt",
                )
            except OSError as exc:
                self._state["status"] = "error"
                self._state["job"] = {"kind": kind, "status": "error", "progress": None, "result": str(exc)}
                self._touch()
                raise RuntimeError(f"could not start job: {exc}") from exc
            process = self._process
            self._state["status"] = "running"
            self._state["job"]["status"] = "running"
            self._touch()
        threading.Thread(
            target=self._read_process, args=(process,), daemon=True,
            name=f"presentation-{kind}",
        ).start()

    def job_action(self, payload: dict[str, Any]) -> None:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None or process.stdin is None:
                raise RuntimeError("no interactive job is running")
            line = json.dumps(payload, ensure_ascii=False) + "\n"
            try:
                process.stdin.write(line)
                process.stdin.flush()
            except OSError as exc:
                raise RuntimeError(f"could not send job action: {exc}") from exc

    def stop_job(self) -> None:
        self.stop_live()

    def stop_live(self) -> None:
        with self._lock:
            process = self._process
            if process is None or process.poll() is not None:
                self._state["status"] = "stopped"
                self._event("No managed process is running", "info", source="system")
                self._touch()
                return
            self._state["status"] = "stopping"
            self._event("Stopping the active process…", "warning", source="system")
            self._touch()
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGINT)
            else:
                process.terminate()
        except (OSError, ProcessLookupError):
            pass

    def close(self) -> None:
        """Best-effort child cleanup when the presentation server exits."""

        with self._lock:
            process = self._process
        if process is None or process.poll() is not None:
            return
        try:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            try:
                process.kill()
            except OSError:
                pass

    def accepts_token(self, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(str(token), self._telemetry_token)

    def ingest_frame(self, body: bytes) -> None:
        if not body or len(body) > 2_500_000:
            raise ValueError("invalid telemetry frame")
        with self._lock:
            self._frame = bytes(body)
            self._frame_version += 1
            self._state["frame_version"] = self._frame_version
            self._touch()

    def ingest_telemetry(self, payload: dict[str, Any]) -> None:
        kind = str(payload.get("type", ""))
        with self._lock:
            if kind == "stage":
                self._set_step(
                    str(payload.get("step", "")), str(payload.get("status", "pending")),
                    str(payload.get("detail", "")),
                )
                if payload.get("identity"):
                    self._state["identity"] = {
                        "id": payload["identity"], "modality": payload.get("modality"),
                        "similarity": payload.get("similarity"), "is_new": payload.get("is_new"),
                    }
            elif kind == "sensor":
                name = str(payload.get("sensor", ""))
                if name in self._state["sensors"]:
                    active = bool(payload.get("active"))
                    self._state["sensors"][name] = active
                    if not active and name == "camera":
                        self._frame = None
                        self._frame_version += 1
                        self._state["frame_version"] = self._frame_version
            elif kind == "metric":
                name = str(payload.get("name", ""))
                if name:
                    self._state["metrics"][name] = payload.get("value")
                    for extra in ("progress", "remaining_s"):
                        if extra in payload:
                            self._state["metrics"][f"{name}_{extra}"] = payload[extra]
            elif kind == "outcome":
                self._state["outcome"] = str(payload.get("detail") or payload.get("outcome") or "Complete")
                self._state["headline"] = "Delivery complete"
            elif kind == "frame_clear":
                self._frame = None
                self._frame_version += 1
                self._state["frame_version"] = self._frame_version
            elif kind == "job_progress":
                self._state["job"]["progress"] = payload.get("progress")
                self._state["job"]["result"] = payload.get("detail")
            elif kind == "job_result":
                self._state["job"]["result"] = payload.get("result", payload.get("detail"))
            elif kind == "reminder_draft":
                self._state["reminder_draft"] = {
                    key: payload.get(key)
                    for key in ("text", "remind_at", "sensitive", "backend", "reason")
                }
                self._state["job"]["result"] = "Draft ready for review"
            else:
                return
            message = payload.get("detail")
            if message:
                self._event(str(message), "live", source="telemetry")
            self._touch()

    def _read_process(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is not None:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if line:
                    self.ingest_live_line(line)
        return_code = process.wait()
        with self._lock:
            was_job = self._state.get("mode") == "job"
            job_kind = self._state.get("job", {}).get("kind")
            if self._process is process:
                self._process = None
            if self._state["status"] == "stopping" or return_code in {0, 130, -signal.SIGINT}:
                self._state["status"] = "stopped"
                self._state["headline"] = (
                    f"{str(job_kind).replace('_', ' ').title()} complete"
                    if was_job and return_code == 0 else "Process stopped"
                )
                tone = "info"
            else:
                self._state["status"] = "error"
                self._state["headline"] = "Managed process exited unexpectedly"
                tone = "error"
            if was_job:
                self._state["job"]["status"] = "complete" if return_code == 0 else (
                    "stopped" if return_code in {130, -signal.SIGINT} else "error"
                )
                self._state["job"]["progress"] = 1.0 if return_code == 0 else self._state["job"].get("progress")
            else:
                self._state["job"] = {"kind": "live", "status": "stopped", "progress": None, "result": None}
            self._event(f"Process exited with code {return_code}", tone, source="job" if was_job else "live")
            self._frame = None
            self._frame_version += 1
            self._state["frame_version"] = self._frame_version
            self._state["sensors"] = {"microphone": False, "camera": False}
            self._touch()

    def ingest_live_line(self, line: str) -> None:
        """Translate existing engine output into visible stages.

        The raw line is always preserved in the on-screen evidence log.  Pattern
        matching only enriches the display; it never influences the live engine.
        """

        lower = line.lower()
        with self._lock:
            tone = "error" if "error" in lower or "failed" in lower else (
                "warning" if "warning" in lower or "withhold" in lower else "live"
            )
            self._event(line, tone, source="engine")

            if line.startswith("[config]") or "consent policy:" in lower:
                self._set_step("configuration", "complete", "Live condition accepted by reminder_app.")
                self._set_step("reminder", "active", "Waiting for a pending reminder to approach its scheduled time.")
            if "reminder found:" in lower or " approaching (scheduled " in lower:
                self._set_step("reminder", "complete", line.replace("[info-status] ", ""))
                self._set_step("sensitivity", "active", "Checking the reminder's sensitivity label.")
            if "sensitivity =" in lower:
                self._set_step("sensitivity", "complete", line)
                self._set_step("owner", "active", "Checking whether the watch is connected.")
            if "owner is in the room" in lower:
                self._set_step("owner", "complete", "Watch connected — owner presence confirmed.")
            elif "owner is not in the room" in lower or "owner not present" in lower:
                self._set_step("owner", "warning", "Owner/watch absent — reminder is held and sensors stay off.")
            if "not sensitive - skipping" in lower:
                for step in ("microphone", "camera", "identity", "consent", "memory"):
                    self._set_step(step, "skipped", "Bypassed for non-sensitive content.")
                self._set_step("delivery", "active", "Preparing normal spoken delivery.")
            if "sensor 1/2 - mic" in lower or "listening continuously" in lower:
                self._set_step("microphone", "active", line)
            if "mic found no bystander" in lower or "only the owner was heard" in lower:
                self._set_step("microphone", "complete", "No non-owner voice detected; raw audio discarded.")
                if self._state["config"].get("sensors") == "both":
                    self._set_step("camera", "active", "Microphone clear — waiting for the fallback scan.")
                else:
                    self._set_step("camera", "skipped", "Mic-only condition; camera remains closed.")
            if "sensor 2/2 - camera" in lower or "double-checking the room" in lower:
                self._set_step("camera", "active", line)
            if "camera saw no bystander" in lower or "neither heard nor saw" in lower:
                self._set_step("camera", "complete", "No bystander seen; camera closed.")
                self._set_step("identity", "skipped", "No bystander to identify.")
                self._set_step("consent", "skipped", "Owner alone; no consent prompt needed.")
                self._set_step("delivery", "active", "Preparing owner-alone delivery.")
            if "camera check failed" in lower or "no usable view" in lower:
                self._set_step("camera", "warning", line)
            if "bystander" in lower and ("present" in lower or "recognise" in lower or "recognize" in lower):
                if "mic" in lower or "heard" in lower:
                    self._set_step("microphone", "complete", "Bystander voice detected; raw audio discarded.")
                    self._set_step("camera", "skipped", "Mic hit — camera remains closed.")
                self._set_step("identity", "complete", line.replace("[info-status] ", ""))
                self._set_step("consent", "active", "Resolving disclosure permission for this person.")
            if "asking the owner on the watch" in lower:
                self._set_step("consent", "active", "Consent prompt is visible privately on the Bangle.js watch.")
            if "remembered yes" in lower or "watch said yes" in lower:
                self._set_step("consent", "complete", "Disclosure permitted: Yes.")
                self._set_step("delivery", "active", "Preparing spoken delivery.")
            if "remembered no" in lower or "watch said no" in lower or "no watch answer" in lower:
                self._set_step("consent", "complete", "Disclosure not permitted; use private delivery.")
                self._set_step("delivery", "active", "Preparing private wrist delivery.")
            if "saving the owner's answer" in lower:
                self._set_step("memory", "active", "Persisting the explicit answer under the local bystander ID.")
            if "reminder disclose" in lower or "speaking the reminder" in lower:
                self._set_step("delivery", "complete", line)
                self._state["outcome"] = "Reminder spoken aloud"
            if "private note" in lower or "privately to the wrist" in lower:
                self._set_step("delivery", "complete", line)
                self._state["outcome"] = "Reminder delivered privately to the wrist"
            if "not stored" in lower and self._state["config"].get("policy") == "reask":
                self._set_step("memory", "skipped", "Re-ask condition stores no consent answer.")
            self._touch()


class PresentationHTTPServer(ThreadingHTTPServer):
    controller: PresentationController


class PresentationRequestHandler(BaseHTTPRequestHandler):
    """Static-file + JSON handler with a deliberately small route surface."""

    server: PresentationHTTPServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Keep the laptop terminal calm during polling; application errors are
        # returned to the UI and the launch URL is printed explicitly.
        return

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/state":
            self._send_json(self.server.controller.snapshot())
            return
        if path == "/api/scenarios":
            self._send_json({"scenarios": SCENARIOS, "steps": STEP_DEFINITIONS})
            return
        if path == "/api/readiness":
            self._send_json(readiness_snapshot())
            return
        if path == "/api/algorithms":
            self._send_json(benchmark_snapshot())
            return
        if path == "/api/evaluation":
            self._send_json(evaluation_snapshot())
            return
        if path == "/api/frame":
            body, version = self.server.controller.frame_snapshot()
            if body is None:
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("ETag", f'"{version}"')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/api/health":
            self._send_json({"ok": True})
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path in {"/api/internal/event", "/api/internal/frame"}:
                if not self.server.controller.accepts_token(self.headers.get("X-Thesis-Token")):
                    self._send_json({"error": "unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
                if path.endswith("/frame"):
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                    except ValueError as exc:
                        raise ValueError("invalid Content-Length") from exc
                    if not 0 < length <= 2_500_000:
                        raise ValueError("telemetry frame is too large")
                    self.server.controller.ingest_frame(self.rfile.read(length))
                else:
                    self.server.controller.ingest_telemetry(self._read_json())
                self._send_json({"ok": True})
                return
            payload = self._read_json()
            if path == "/api/demo/start":
                scenario = str(payload.pop("scenario", "voice_decline"))
                self.server.controller.start_demo(scenario, payload)
            elif path == "/api/demo/next":
                self.server.controller.advance_demo()
            elif path == "/api/demo/previous":
                self.server.controller.previous_demo()
            elif path == "/api/reset":
                self.server.controller.reset()
            elif path == "/api/live/start":
                self.server.controller.start_live(payload)
            elif path == "/api/live/stop":
                self.server.controller.stop_live()
            elif path == "/api/reminders/save":
                reminder = self.server.controller.save_reminder(payload)
                self._send_json({"reminder": reminder, "state": self.server.controller.snapshot()})
                return
            elif path == "/api/jobs/start":
                kind = str(payload.pop("kind", ""))
                self.server.controller.start_job(kind, payload)
            elif path == "/api/jobs/action":
                self.server.controller.job_action(payload)
            elif path == "/api/jobs/stop":
                self.server.controller.stop_job()
            else:
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            self._send_json(self.server.controller.snapshot())
        except ValueError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
        except Exception as exc:  # keep the local UI recoverable and informative
            self._send_json({"error": f"unexpected server error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _serve_static(self, request_path: str) -> None:
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "text/javascript; charset=utf-8"),
            "/stage": ("stage.html", "text/html; charset=utf-8"),
            "/stage.html": ("stage.html", "text/html; charset=utf-8"),
            "/stage.css": ("stage.css", "text/css; charset=utf-8"),
            "/stage.js": ("stage.js", "text/javascript; charset=utf-8"),
        }
        item = files.get(request_path)
        if item is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        filename, content_type = item
        path = UI_DIR / filename
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or mimetypes.guess_type(path.name)[0])
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'")
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the local thesis presentation console.")
    parser.add_argument("--port", type=int, default=8765, help="loopback port (default: 8765; use 0 for any free port)")
    parser.add_argument("--no-open", action="store_true", help="do not open the browser automatically")
    return parser


def run_server(port: int = 8765, *, open_browser: bool = True) -> int:
    if not UI_DIR.is_dir():
        raise SystemExit(f"Presentation UI assets are missing: {UI_DIR}")
    if not 0 <= port <= 65_535:
        raise SystemExit("--port must be between 0 and 65535")

    controller = PresentationController()
    try:
        server = PresentationHTTPServer(("127.0.0.1", port), PresentationRequestHandler)
    except OSError as exc:
        raise SystemExit(f"Could not start the presentation UI on port {port}: {exc}") from exc
    server.controller = controller
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}"
    controller.configure_transport(url)

    print("\nThesis presentation console is ready.", flush=True)
    print(f"Open: {url}", flush=True)
    print(f"Stage view (defense demo): {url}/stage", flush=True)
    print("Press Ctrl-C here to stop it.\n", flush=True)
    if open_browser:
        threading.Timer(0.45, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping presentation console…", flush=True)
    finally:
        controller.close()
        server.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_server(args.port, open_browser=not args.no_open)


if __name__ == "__main__":
    sys.exit(main())
