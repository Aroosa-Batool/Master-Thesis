"""Hardware-free tests for the fused engine (``robot.core.fusion_reminder``).

Covers the mic-first/camera-second priority, the camera opening only in
both-sensor mode after a mic miss, the fail-safe handling of an inconclusive
camera check, the sweep pacing across the pre-reminder window, the fusion
consent-cache namespace, and camera cleanup / head recentering on success and
failure.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

import robot.core.fusion_reminder as fr
import robot.core.robot_io as demo
import robot.core.voice_reminder as vr
from robot.core.head_scan import HEAD_CENTRE, HeadScanner
from robot.core.policy import ConsentKey, ConsentStore
from tests.conftest import FakeWatch, Spy, make_reminder


def _mic_bystander():
    return fr.Bystander(raw_id="person_001", modality=fr.MODALITY_MIC)


# ------------------------------------------------------- sensor priority ----

def test_mic_hit_skips_the_camera(monkeypatch):
    camera_spy = Spy(result=(None, True))
    monkeypatch.setattr(fr, "check_mic", lambda *a, **k: _mic_bystander())
    monkeypatch.setattr(fr, "check_camera", camera_spy)
    rem = make_reminder()
    found, conclusive = fr.sense_presence(
        rem, rem.remind_at_dt, None, None, None,
        object(), object(), object(),        # camera stage IS available
        record_s=1.0,
    )
    assert found is not None and found.modality == fr.MODALITY_MIC
    assert conclusive is True
    assert not camera_spy.called             # the camera was never consulted


def test_mic_miss_invokes_camera_only_in_both_sensor_mode(monkeypatch):
    camera_spy = Spy(result=(None, True))
    monkeypatch.setattr(fr, "check_mic", lambda *a, **k: None)
    monkeypatch.setattr(fr, "check_camera", camera_spy)
    rem = make_reminder()

    # Mic-only (no face stack): the camera stage is skipped entirely.
    found, conclusive = fr.sense_presence(
        rem, rem.remind_at_dt, None, None, None, None, None, None,
        record_s=1.0,
    )
    assert (found, conclusive) == (None, True)
    assert not camera_spy.called

    # Both-sensor mode: the mic miss escalates to the camera.
    found, conclusive = fr.sense_presence(
        rem, rem.remind_at_dt, None, None, None,
        object(), object(), object(),
        record_s=1.0,
    )
    assert (found, conclusive) == (None, True)
    assert camera_spy.called


def test_camera_sweep_is_paced_to_end_just_before_the_due_time(monkeypatch):
    monkeypatch.setattr(fr, "check_mic", lambda *a, **k: None)
    camera_spy = Spy(result=(None, True))
    monkeypatch.setattr(fr, "check_camera", camera_spy)
    rem = make_reminder(due_in_s=60.0)
    before = time.monotonic()
    fr.sense_presence(rem, rem.remind_at_dt, None, None, None,
                      object(), object(), object(), record_s=1.0)
    after = time.monotonic()
    finish_by = camera_spy.calls[0][0][4]
    # The sweep deadline lands SCAN_MARGIN_S before the due time (60s away).
    assert finish_by is not None
    expected = 60.0 - fr.SCAN_MARGIN_S
    assert before + expected - 1.0 <= finish_by <= after + expected + 1.0


def test_camera_sweep_is_unpaced_when_the_due_time_has_passed(monkeypatch):
    # Legacy mode: the mic records right up to T, so the camera runs after it
    # with no window left - the sweep must run at its natural pace, not dwell.
    monkeypatch.setattr(fr, "check_mic", lambda *a, **k: None)
    camera_spy = Spy(result=(None, True))
    monkeypatch.setattr(fr, "check_camera", camera_spy)
    rem = make_reminder(due_in_s=0.0)
    fr.sense_presence(rem, rem.remind_at_dt, None, None, None,
                      object(), object(), object(), record_s=1.0)
    assert camera_spy.calls[0][0][4] is None


# ---------------------------------------------- inconclusive camera checks ----

def test_camera_open_failure_is_inconclusive_not_owner_alone(monkeypatch):
    def broken_open():
        raise SystemExit("no external camera found")

    monkeypatch.setattr(fr, "open_camera", broken_open)
    found, conclusive = fr.check_camera(make_reminder(), object(), object(),
                                        object())
    assert found is None
    assert conclusive is False


def test_no_usable_frame_is_inconclusive(monkeypatch):
    class BlindSession:
        def __enter__(self):
            self.scanner = type("S", (), {"scan": lambda s: [],
                                          "enabled": False})()
            return self

        def run_scan(self, finish_by=None):
            return []

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(fr, "_CameraSession", BlindSession)
    found, conclusive = fr.check_camera(make_reminder(), object(), object(),
                                        object())
    assert (found, conclusive) == (None, False)


def test_fail_safe_withholds_on_inconclusive_camera(quiet_voice_engine):
    watch = FakeWatch(connected=True)
    status = fr.decide_and_deliver(make_reminder(), None, watch, None,
                                   conclusive=False, fail_safe=True)
    assert "inconclusive" in status
    assert not quiet_voice_engine["spoken"].called   # never spoken aloud
    assert quiet_voice_engine["withheld"].called
    assert watch.notified                            # private note instead
    assert watch.asked == []                         # and no consent prompt


def test_legacy_fail_open_still_reveals_on_inconclusive_camera(
        quiet_voice_engine):
    # The pre-existing fusion apps keep their documented fail-open behaviour.
    watch = FakeWatch(connected=True)
    status = fr.decide_and_deliver(make_reminder(), None, watch, None,
                                   conclusive=False, fail_safe=False)
    assert "owner alone" in status
    assert quiet_voice_engine["spoken"].called


# ------------------------------------------------ consent (fusion namespace) ----

def test_remembered_answers_use_the_modality_prefixed_key(tmp_path,
                                                          quiet_voice_engine):
    store = ConsentStore(tmp_path / "fusion_consent.json")
    store.put(ConsentKey(bystander_id="voice:person_001",
                         content_type=demo.REMINDER_CONTENT_TYPE), False)
    watch = FakeWatch(connected=True)
    status = fr.decide_and_deliver(make_reminder(), _mic_bystander(), watch,
                                   store)
    assert "remembered NO" in status
    assert watch.asked == []
    assert not quiet_voice_engine["spoken"].called
    assert watch.notified


def test_fusion_timeout_is_never_cached(tmp_path, quiet_voice_engine):
    store = ConsentStore(tmp_path / "fusion_consent.json")
    watch = FakeWatch(connected=True, answer=None)
    status = fr.decide_and_deliver(make_reminder(), _mic_bystander(), watch,
                                   store)
    assert "no-reply" in status
    assert store.dump() == {}
    assert not quiet_voice_engine["spoken"].called


def test_fusion_reask_mode_asks_every_time(quiet_voice_engine):
    watch = FakeWatch(connected=True, answer=True)
    for _ in range(2):
        status = fr.decide_and_deliver(make_reminder(), _mic_bystander(),
                                       watch, None)
        assert "asked YES" in status
    assert len(watch.asked) == 2


def test_owner_absent_at_delivery_holds(quiet_voice_engine):
    watch = FakeWatch(connected=False)
    status = fr.decide_and_deliver(make_reminder(), _mic_bystander(), watch,
                                   None)
    assert status is None
    assert not quiet_voice_engine["spoken"].called
    assert watch.asked == []


# ------------------------------------------------- whole-reminder path ----

def test_non_sensitive_reminder_opens_no_sensor(monkeypatch,
                                                quiet_voice_engine):
    record_spy = Spy()
    camera_spy = Spy(result=(None, True))
    monkeypatch.setattr(vr, "record_until", record_spy)
    monkeypatch.setattr(fr, "check_camera", camera_spy)
    rem = make_reminder(due_in_s=0.0, sensitive=False)
    watch = FakeWatch(connected=True)
    status = fr.deliver_due_reminder(rem, watch, None, None, None, None,
                                     object(), object(), object(),
                                     poll_s=0.05, record_s=1.0)
    assert "non-sensitive" in status
    assert not record_spy.called
    assert not camera_spy.called
    assert quiet_voice_engine["spoken"].called


def test_owner_absent_at_wakeup_opens_no_sensor(monkeypatch,
                                                quiet_voice_engine):
    record_spy = Spy()
    camera_spy = Spy(result=(None, True))
    monkeypatch.setattr(vr, "record_until", record_spy)
    monkeypatch.setattr(fr, "check_camera", camera_spy)
    rem = make_reminder(due_in_s=0.0, sensitive=True)
    watch = FakeWatch(connected=False)
    status = fr.deliver_due_reminder(rem, watch, None, None, None, None,
                                     object(), object(), object(),
                                     poll_s=0.05, record_s=1.0)
    assert status is None
    assert not record_spy.called and not camera_spy.called


def test_camera_failure_in_fail_safe_mode_never_discloses(monkeypatch,
                                                          quiet_voice_engine):
    # Mic hears nobody; the camera then fails to open -> the reminder must be
    # withheld privately, never spoken aloud.
    monkeypatch.setattr(fr, "check_mic", lambda *a, **k: None)
    monkeypatch.setattr(fr, "open_camera",
                        Spy(result=None))  # replaced below to raise

    def broken_open(*a, **k):
        raise SystemExit("camera wedged")

    monkeypatch.setattr(fr, "open_camera", broken_open)
    rem = make_reminder(due_in_s=0.0, sensitive=True)
    watch = FakeWatch(connected=True)
    status = fr.deliver_due_reminder(rem, watch, None, None, None, None,
                                     object(), object(), object(),
                                     poll_s=0.05, record_s=1.0,
                                     camera_fail_safe=True)
    assert "inconclusive" in status
    assert not quiet_voice_engine["spoken"].called
    assert watch.notified


# --------------------------------------- camera cleanup + head recentering ----

class FakeCap:
    def __init__(self):
        self.released = False

    def read(self):
        return False, None

    def release(self):
        self.released = True


def test_camera_session_releases_on_success_and_failure(monkeypatch):
    cap = FakeCap()
    monkeypatch.setattr(fr, "open_camera", lambda *a, **k: cap)
    with fr._CameraSession():
        pass
    assert cap.released

    cap2 = FakeCap()
    monkeypatch.setattr(fr, "open_camera", lambda *a, **k: cap2)
    with pytest.raises(RuntimeError):
        with fr._CameraSession():
            raise RuntimeError("scan blew up")
    assert cap2.released


class PreviewCap(FakeCap):
    """Camera that always yields a frame, so run_scan's loop has one to show.

    ``captured`` fires on the first read, so a stubbed sweep can wait for the
    capture loop to have run at least once instead of racing it.
    """

    def __init__(self):
        super().__init__()
        self.reads = 0
        self.captured = threading.Event()

    def read(self):
        self.reads += 1
        self.captured.set()
        return True, np.zeros((8, 8, 3), dtype=np.uint8)


def _preview_session(monkeypatch, cap, shots, preview="1"):
    """A _CameraSession whose sweep returns ``shots``, with cv2 imshow spied."""

    monkeypatch.setenv(fr.CAMERA_PREVIEW_ENV, preview)
    monkeypatch.setattr(fr, "open_camera", lambda *a, **k: cap)
    shown: list[str] = []
    monkeypatch.setattr(fr.cv2, "imshow", lambda name, frame: shown.append(name))
    monkeypatch.setattr(fr.cv2, "waitKey", lambda delay: -1)
    monkeypatch.setattr(fr.cv2, "destroyWindow", lambda name: None)

    def scan(_self, finish_by=None):
        # Stand in for a real sweep: it outlives at least one captured frame.
        assert cap.captured.wait(5.0), "capture loop never read a frame"
        return shots

    session = fr._CameraSession()
    with session as cam:
        cam.scanner = type("S", (), {"scan": scan, "enabled": False})()
        got = cam.run_scan()
    return got, shown


def test_run_scan_previews_while_the_camera_is_open(monkeypatch):
    cap = PreviewCap()
    sentinel = ["shot"]
    got, shown = _preview_session(monkeypatch, cap, sentinel)
    assert got == sentinel                      # sweep result passes through
    assert cap.reads > 0                        # the loop actually captured
    assert shown and shown[0] == fr.CAMERA_PREVIEW_WINDOW
    assert cap.released                         # and the device still closed


def test_camera_preview_can_be_switched_off(monkeypatch):
    cap = PreviewCap()
    got, shown = _preview_session(monkeypatch, cap, [], preview="0")
    assert got == []
    assert shown == []                          # CAMERA_PREVIEW=0 -> no window
    assert cap.released


def test_a_sweep_failure_still_reaches_the_caller(monkeypatch):
    monkeypatch.setenv(fr.CAMERA_PREVIEW_ENV, "0")
    cap = PreviewCap()
    monkeypatch.setattr(fr, "open_camera", lambda *a, **k: cap)

    def boom(_self, finish_by=None):
        raise RuntimeError("sweep died on the worker thread")

    with pytest.raises(RuntimeError):
        with fr._CameraSession() as cam:
            cam.scanner = type("S", (), {"scan": boom, "enabled": False})()
            cam.run_scan()
    assert cap.released


class StubLatest:
    """LatestFrame stand-in that always has a fresh frame (or raises)."""

    def __init__(self, fail=False):
        self.fail = fail
        self.frame = np.zeros((4, 4, 3), dtype=np.uint8)

    def start(self):
        pass

    def stop(self):
        pass

    def get_after(self, moment, timeout):
        if self.fail:
            raise RuntimeError("camera died mid-sweep")
        return self.frame


def test_head_recenters_after_a_successful_sweep():
    moves: list[float] = []
    scanner = HeadScanner(StubLatest(), moves.append,
                          positions=(2.0, 5.0, 8.0), settle_s=0.0,
                          frame_timeout_s=0.1)
    shots = scanner.scan()
    assert [s.position for s in shots] == [2.0, 5.0, 8.0]
    assert moves[-1] == HEAD_CENTRE                  # faced forward again


def test_sweep_with_finish_by_dwells_to_fill_the_window():
    moves: list[float] = []
    scanner = HeadScanner(StubLatest(), moves.append,
                          positions=(2.0, 5.0, 8.0), settle_s=0.0,
                          frame_timeout_s=0.1)
    start = time.monotonic()
    shots = scanner.scan(finish_by=start + 0.9)
    elapsed = time.monotonic() - start
    assert [s.position for s in shots] == [2.0, 5.0, 8.0]
    assert elapsed >= 0.8      # the sweep filled the window instead of rushing
    assert moves[-1] == HEAD_CENTRE


def test_head_recenters_even_when_the_sweep_fails():
    moves: list[float] = []
    scanner = HeadScanner(StubLatest(fail=True), moves.append,
                          positions=(2.0, 5.0, 8.0), settle_s=0.0,
                          frame_timeout_s=0.1)
    with pytest.raises(RuntimeError):
        scanner.scan()
    assert moves[-1] == HEAD_CENTRE
