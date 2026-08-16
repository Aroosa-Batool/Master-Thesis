from __future__ import annotations

import csv
import datetime as dt
import json
import signal

import numpy as np
import pytest

from robot.apps import presentation_ui as ui
from robot.core import presentation_telemetry


def test_workflow_order_matches_live_pipeline():
    assert [step["id"] for step in ui.STEP_DEFINITIONS] == [
        "configuration", "reminder", "sensitivity", "owner", "microphone",
        "camera", "identity", "consent", "memory", "delivery",
    ]


@pytest.mark.parametrize("scenario", sorted(ui.SCENARIOS))
def test_every_guided_scenario_reaches_a_delivery_outcome(scenario):
    meta = ui.SCENARIOS[scenario]
    controller = ui.PresentationController()
    controller.start_demo(scenario, {
        "policy": meta["recommended_policy"],
        "sensors": meta["recommended_sensors"],
    })
    while controller.snapshot()["demo"]["has_next"]:
        controller.advance_demo()
    state = controller.snapshot()
    assert state["status"] == "complete"
    assert state["outcome"]
    delivery = next(step for step in state["steps"] if step["id"] == "delivery")
    assert delivery["status"] == "complete"


def test_guided_previous_replays_to_the_prior_cursor():
    controller = ui.PresentationController()
    controller.start_demo("voice_decline", {"policy": "remember", "sensors": "both"})
    controller.advance_demo()
    controller.advance_demo()
    assert controller.snapshot()["demo"]["cursor"] == 2
    controller.previous_demo()
    state = controller.snapshot()
    assert state["demo"]["cursor"] == 1
    assert state["demo"]["has_next"] is True


def test_telemetry_updates_sensors_metrics_identity_and_clears_frame():
    controller = ui.PresentationController()
    controller.ingest_frame(b"jpeg")
    assert controller.snapshot()["frame_available"] is True
    controller.ingest_telemetry({"type": "sensor", "sensor": "camera", "active": True})
    controller.ingest_telemetry({"type": "metric", "name": "head_position", "value": "2/10"})
    controller.ingest_telemetry({
        "type": "stage", "step": "identity", "status": "complete",
        "detail": "Found person", "identity": "person_001", "modality": "face",
    })
    state = controller.snapshot()
    assert state["sensors"]["camera"] is True
    assert state["metrics"]["head_position"] == "2/10"
    assert state["identity"]["id"] == "person_001"
    controller.ingest_telemetry({"type": "sensor", "sensor": "camera", "active": False})
    assert controller.snapshot()["frame_available"] is False


def test_telemetry_token_is_required():
    controller = ui.PresentationController()
    assert controller.accepts_token(None) is False
    assert controller.accepts_token("wrong") is False
    assert controller.accepts_token(controller._telemetry_token) is True


def test_telemetry_throttles_frames_and_drops_stale_queue_items():
    transport = presentation_telemetry._Transport()
    transport.enabled = True
    transport._start = lambda: None
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    transport.frame(frame, max_fps=1.0)
    transport.frame(frame, max_fps=1.0)
    assert transport._queue.qsize() == 1

    while not transport._queue.empty():
        transport._queue.get_nowait()
        transport._queue.task_done()
    for index in range(60):
        transport.enqueue("/api/internal/frame", str(index).encode(), {})
    assert transport._queue.qsize() == 48
    bodies = []
    while not transport._queue.empty():
        _path, body, _headers = transport._queue.get_nowait()
        bodies.append(body)
        transport._queue.task_done()
    assert bodies[0] == b"12"
    assert bodies[-1] == b"59"


@pytest.mark.parametrize("payload", [
    {"policy": "remember", "sensors": "both", "monitor_lead": 90,
     "listen_duration": 45, "laptop_voice": "true"},
    {"policy": "remember", "sensors": "both", "monitor_lead": float("nan"),
     "listen_duration": 45, "laptop_voice": True},
    {"policy": "remember", "sensors": "both", "monitor_lead": 30,
     "listen_duration": 45, "laptop_voice": True},
])
def test_live_config_rejects_invalid_types_and_timing(payload):
    with pytest.raises(ValueError):
        ui._validate_config(payload, live=True)


def test_single_active_job_lane_and_process_group_cancellation(monkeypatch):
    class RunningProcess:
        pid = 4321

        @staticmethod
        def poll():
            return None

    controller = ui.PresentationController()
    controller._process = RunningProcess()
    with pytest.raises(RuntimeError):
        controller.start_job("device_camera", {})

    signals = []
    monkeypatch.setattr(ui.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    controller.stop_job()
    assert signals == [(4321, signal.SIGINT)]


LIVE_REQUEST = {
    "policy": "remember", "sensors": "both", "monitor_lead": 90,
    "listen_duration": 45, "laptop_voice": True,
}


def test_live_run_needs_a_pending_reminder(monkeypatch):
    monkeypatch.setattr(ui, "readiness_snapshot", lambda: {
        "voice": {"ready": True}, "face": {"ready": True},
        "next_reminder": None, "pending_reminders": [],
    })
    with pytest.raises(ValueError, match="no pending reminder"):
        ui.PresentationController().start_live(dict(LIVE_REQUEST))


def test_live_run_pins_itself_to_the_next_pending_reminder(monkeypatch):
    soonest = {"id": "rem_002", "text": "therapy", "remind_at": "2026-08-15T19:00:00",
               "sensitive": True, "seconds_until": 120.0}
    monkeypatch.setattr(ui, "readiness_snapshot", lambda: {
        "voice": {"ready": True}, "face": {"ready": True},
        "next_reminder": soonest,
        "pending_reminders": [soonest, {"id": "rem_007", "text": "later"}],
    })
    captured: dict[str, list[str]] = {}

    class FakeProcess:
        pid = 99
        stdout = []

        def poll(self):
            return None

        def wait(self):
            return 0

    def fake_popen(command, **_kwargs):
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(ui.subprocess, "Popen", fake_popen)
    controller = ui.PresentationController()
    controller.start_live(dict(LIVE_REQUEST))

    command = captured["command"]
    assert command[command.index("--reminder-id") + 1] == "rem_002"
    # The pinned reminder travels in the state so the countdown cannot drift to
    # a different one mid-run.
    assert controller.snapshot()["config"]["reminder"]["id"] == "rem_002"


def test_next_reminder_steps_over_undelivered_leftovers(monkeypatch, tmp_path):
    now = dt.datetime.now()
    store = tmp_path / "reminders.json"
    store.write_text(json.dumps({"reminders": [
        {"id": "rem_001", "text": "stale", "delivered": False,
         "remind_at": (now - dt.timedelta(hours=2)).isoformat(timespec="seconds")},
        {"id": "rem_002", "text": "soon", "delivered": False, "sensitive": True,
         "remind_at": (now + dt.timedelta(minutes=3)).isoformat(timespec="seconds")},
        {"id": "rem_003", "text": "later", "delivered": False,
         "remind_at": (now + dt.timedelta(hours=1)).isoformat(timespec="seconds")},
        {"id": "rem_004", "text": "done", "delivered": True,
         "remind_at": (now + dt.timedelta(minutes=1)).isoformat(timespec="seconds")},
    ]}), encoding="utf-8")
    monkeypatch.setattr(ui, "REMINDERS_PATH", store)

    readiness = ui.readiness_snapshot()
    assert readiness["next_reminder"]["id"] == "rem_002"
    assert readiness["upcoming_count"] == 2
    assert readiness["overdue_count"] == 1
    assert "overdue" in readiness["reminders"]["detail"]


def test_next_reminder_falls_back_to_a_stale_one_when_nothing_is_ahead(monkeypatch, tmp_path):
    store = tmp_path / "reminders.json"
    store.write_text(json.dumps({"reminders": [
        {"id": "rem_009", "text": "stale", "delivered": False,
         "remind_at": "2020-01-01T09:00:00"},
    ]}), encoding="utf-8")
    monkeypatch.setattr(ui, "REMINDERS_PATH", store)

    readiness = ui.readiness_snapshot()
    assert readiness["next_reminder"]["id"] == "rem_009"
    assert readiness["upcoming_count"] == 0
    assert readiness["reminders"]["ready"] is False


def test_pending_entry_reports_seconds_until_and_flags_overdue():
    soon = ui._pending_entry({
        "id": "rem_001", "text": "doctor", "sensitive": True,
        "remind_at": (dt.datetime.now() + dt.timedelta(seconds=90)).isoformat(timespec="seconds"),
    })
    assert 60 < soon["seconds_until"] <= 90
    overdue = ui._pending_entry({
        "id": "rem_002", "text": "past", "remind_at": "2020-01-01T00:00:00",
    })
    assert overdue["seconds_until"] < 0
    assert ui._pending_entry({"id": "rem_003", "remind_at": "not-a-date"})["seconds_until"] is None


def test_benchmark_job_uses_isolated_output_directory(monkeypatch):
    captured = {}

    class FakeProcess:
        pid = 123
        stdin = None
        stdout = []

        @staticmethod
        def poll():
            return None

    def fake_popen(command, **_kwargs):
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(ui.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ui.threading.Thread, "start", lambda _self: None)
    ui.PresentationController().start_job("benchmark_camera", {
        "candidates": "yunet", "repeats": 2, "timeout": 10,
        "resolution": "640x480", "use_eval_data": False,
    })
    command = captured["command"]
    out_dir = command[command.index("--out-dir") + 1]
    assert "benchmark_runs" in out_dir
    assert "robot/bench/results" not in out_dir


def test_manual_reminder_save_validates_and_persists(monkeypatch, tmp_path):
    path = tmp_path / "reminders.json"
    monkeypatch.setattr(ui, "REMINDERS_PATH", path)
    controller = ui.PresentationController()
    when = dt.datetime.now() + dt.timedelta(minutes=5)
    saved = controller.save_reminder({
        "text": "Doctor appointment",
        "remind_at": when.isoformat(timespec="minutes"),
        "sensitive": True,
    })
    assert saved["id"] == "rem_001"
    assert saved["sensitive"] is True
    assert saved["remind_at"].endswith(":00")
    assert path.exists()


@pytest.mark.parametrize("payload", [
    {"text": "", "remind_at": "2030-01-01T10:00", "sensitive": True},
    {"text": "test", "remind_at": "not-a-time", "sensitive": True},
    {"text": "test", "remind_at": "2020-01-01T10:00", "sensitive": True},
    {"text": "test", "remind_at": "2030-01-01T10:00", "sensitive": "yes"},
])
def test_manual_reminder_validation(payload):
    with pytest.raises(ValueError):
        ui.PresentationController().save_reminder(payload)


def test_benchmark_csv_parser_handles_blank_numbers_and_failure(tmp_path):
    path = tmp_path / "camera_results.csv"
    fields = [
        "name", "stage", "ok", "init_ms", "lat_median_ms", "lat_p95_ms",
        "lat_mean_ms", "fps", "rtf", "peak_rss_mb", "model_size_mb",
        "embedding_dim", "deploy", "accuracy", "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"name": "yunet", "stage": "detect", "ok": "True", "lat_median_ms": "5.2"})
        writer.writerow({"name": "broken", "stage": "detect", "ok": "False", "error": "missing model",
                         "accuracy": '{"detection_rate": 0.875}'})
    rows = ui._read_benchmark_csv(path, "test")
    assert rows[0]["lat_median_ms"] == 5.2
    assert rows[0]["accuracy"] == ""
    assert rows[1]["ok"] is False
    assert rows[1]["peak_rss_mb"] is None
    assert rows[1]["accuracy_value"] == 87.5


def test_evaluation_snapshot_reports_conditions(monkeypatch, tmp_path):
    root = tmp_path / "robot" / "bench" / "eval_data"
    face_dir = root / "faces" / "alice"
    voice_dir = root / "voices" / "alice"
    face_dir.mkdir(parents=True)
    voice_dir.mkdir(parents=True)
    for name in ("near_01.jpg", "far_02.jpg"):
        (face_dir / name).write_bytes(b"x")
    (voice_dir / "quiet_01.wav").write_bytes(b"x")
    monkeypatch.setattr(ui, "PROJECT_ROOT", tmp_path)
    result = ui.evaluation_snapshot()
    assert result["faces"]["alice"]["samples"] == 2
    assert result["faces"]["alice"]["conditions"] == ["far", "near"]
    assert result["voices"]["alice"]["conditions"] == ["quiet"]
