"""Hardware-free tests for the voice engine (``robot.core.voice_reminder``).

The mic is a fake ``sounddevice``; the analysis, speech and robot behaviours
are monkeypatched; the watch is ``FakeWatch``. Covers the T-7min/5min timing
split, sensors staying off for non-sensitive reminders, consent reuse vs
re-ask, timeout non-caching, owner-absence holds, and audio-failure safety.
"""

from __future__ import annotations

import datetime

import numpy as np
import pytest

import robot.core.robot_io as demo
import robot.core.voice_reminder as vr
from robot.core.policy import ConsentKey, ConsentStore
from robot.core.reminders import ReminderStore
from robot.perception.voice_id import VOICE_SR
from tests.conftest import FakeWatch, Spy, make_reminder


# ---------------------------------------------------------------- timing ----

def test_plan_record_seconds_unified_defaults():
    # Woken at T-420s with a 300 s listen duration -> record exactly 300 s.
    assert vr._plan_record_seconds(420.0, 300.0) == 300.0


def test_plan_record_seconds_legacy_records_until_due():
    assert vr._plan_record_seconds(420.0, None) == 420.0


def test_plan_record_seconds_clips_to_the_time_left():
    # Picked up late (only 100 s to T): never still recording after T.
    assert vr._plan_record_seconds(100.0, 300.0) == 100.0


def test_plan_record_seconds_past_due_still_records_minimum():
    assert vr._plan_record_seconds(-10.0, 300.0) == vr.MIN_RECORD_S
    assert vr._plan_record_seconds(2.0, None) == vr.MIN_RECORD_S


class FakeSD:
    """Fake ``sounddevice``: rec() returns silence, wait() is instant."""

    def __init__(self):
        self.rec_frames: list[int] = []

    def rec(self, frames, samplerate, channels, dtype):
        self.rec_frames.append(frames)
        return np.zeros((frames, channels), dtype=np.float32)

    def wait(self):
        pass


def test_record_until_records_exact_duration_and_stops_before_due(monkeypatch):
    fake = FakeSD()
    monkeypatch.setattr(vr, "sd", fake)
    monkeypatch.setattr(vr, "MIN_RECORD_S", 0.0)
    remind_at = datetime.datetime.now() + datetime.timedelta(seconds=1.5)
    audio = vr.record_until(remind_at, "rem_t", record_s=0.1)
    # Requested exactly the configured duration from the mic...
    assert fake.rec_frames == [int(0.1 * VOICE_SR)]
    assert len(audio) == int(0.1 * VOICE_SR)
    # ...and returned well before the due time (mic closes at ~T-1.4s here).
    assert datetime.datetime.now() < remind_at


def test_record_until_legacy_runs_to_the_due_time(monkeypatch):
    fake = FakeSD()
    monkeypatch.setattr(vr, "sd", fake)
    monkeypatch.setattr(vr, "MIN_RECORD_S", 0.0)
    remind_at = datetime.datetime.now() + datetime.timedelta(seconds=0.3)
    vr.record_until(remind_at, "rem_t", record_s=None)
    # Legacy mode records the whole remaining window (~0.3 s) and ends at ~T.
    assert 0 < fake.rec_frames[0] <= int(0.35 * VOICE_SR)
    assert datetime.datetime.now() >= remind_at - datetime.timedelta(
        milliseconds=50)


def test_wake_up_lead_selects_reminders_seven_minutes_early(tmp_path):
    # The run loop treats a reminder as due when now + lead >= its time; with
    # the unified default lead of 420 s a reminder 400 s away is picked up, one
    # 500 s away is not.
    store = ReminderStore(tmp_path / "reminders.json")
    now = datetime.datetime.now()
    soon = store.add("a", now + datetime.timedelta(seconds=400), sensitive=True)
    store.add("b", now + datetime.timedelta(seconds=500), sensitive=True)
    due = store.due(now + datetime.timedelta(seconds=420))
    assert [r.id for r in due] == [soon.id]


# ------------------------------------------------- consent (mic modality) ----

def _key(bystander="person_001"):
    return ConsentKey(bystander_id=bystander,
                      content_type=demo.REMINDER_CONTENT_TYPE)


def _monitored(monkeypatch, watch, consent_store, bystander="person_001",
               silence_len=VOICE_SR):
    """Run monitor_and_deliver with the mic and analysis faked out."""

    monkeypatch.setattr(
        vr, "record_until",
        lambda *a, **k: np.zeros(silence_len, dtype=np.float32))
    monkeypatch.setattr(vr, "analyse_presence", lambda *a, **k: bystander)
    rem = make_reminder(due_in_s=0.0)
    return vr.monitor_and_deliver(
        rem, rem.remind_at_dt, watch, consent_store,
        None, None, None, record_s=1.0, poll_s=0.05,
    )


def test_remembered_yes_is_reused_without_asking(monkeypatch, tmp_path,
                                                 quiet_voice_engine):
    store = ConsentStore(tmp_path / "consent.json")
    store.put(_key(), True)
    watch = FakeWatch(connected=True)
    status = _monitored(monkeypatch, watch, store)
    assert "remembered YES" in status
    assert watch.asked == []                      # no re-prompt
    assert quiet_voice_engine["spoken"].called    # disclosed aloud
    assert not quiet_voice_engine["withheld"].called


def test_remembered_no_is_reused_without_asking(monkeypatch, tmp_path,
                                                quiet_voice_engine):
    store = ConsentStore(tmp_path / "consent.json")
    store.put(_key(), False)
    watch = FakeWatch(connected=True)
    status = _monitored(monkeypatch, watch, store)
    assert "remembered NO" in status
    assert watch.asked == []
    assert not quiet_voice_engine["spoken"].called
    assert quiet_voice_engine["withheld"].called
    assert watch.notified                          # private note instead


def test_cache_miss_asks_and_stores_only_explicit_answers(monkeypatch, tmp_path,
                                                          quiet_voice_engine):
    store = ConsentStore(tmp_path / "consent.json")
    watch = FakeWatch(connected=True, answer=True)
    status = _monitored(monkeypatch, watch, store)
    assert "asked YES" in status
    assert len(watch.asked) == 1
    assert store.get(_key()) is True


def test_reask_mode_never_reads_or_writes_consent_state(monkeypatch,
                                                        quiet_voice_engine):
    # consent_store=None IS the re-ask policy: there is no store object at all,
    # so nothing can be read or written; the watch is asked every single time.
    watch = FakeWatch(connected=True, answer=True)
    for _ in range(2):
        status = _monitored(monkeypatch, watch, None)
        assert "asked YES" in status
    assert len(watch.asked) == 2


def test_timeout_is_never_cached(monkeypatch, tmp_path, quiet_voice_engine):
    store = ConsentStore(tmp_path / "consent.json")
    watch = FakeWatch(connected=True, answer=None)   # no reply / timeout
    status = _monitored(monkeypatch, watch, store)
    assert "no-reply" in status
    assert store.dump() == {}                        # nothing cached
    assert not (tmp_path / "consent.json").exists()  # never even written
    assert not quiet_voice_engine["spoken"].called   # not disclosed aloud
    assert watch.notified                            # private note sent


def test_owner_absent_at_delivery_holds_the_reminder(monkeypatch,
                                                     quiet_voice_engine):
    watch = FakeWatch(connected=False)
    status = _monitored(monkeypatch, watch, None)
    assert status is None
    assert not quiet_voice_engine["spoken"].called
    assert not quiet_voice_engine["withheld"].called


# --------------------------------------------- whole-reminder delivery path ----

def test_non_sensitive_reminder_never_opens_the_mic(monkeypatch,
                                                    quiet_voice_engine):
    record_spy = Spy()
    monkeypatch.setattr(vr, "record_until", record_spy)
    rem = make_reminder(due_in_s=0.0, sensitive=False)
    watch = FakeWatch(connected=True)
    status = vr.deliver_due_reminder(rem, watch, None, None, None, None,
                                     poll_s=0.05, record_s=1.0)
    assert "non-sensitive" in status
    assert not record_spy.called                     # mic never opened
    assert quiet_voice_engine["spoken"].called


def test_owner_absent_at_wakeup_holds_without_opening_the_mic(
        monkeypatch, quiet_voice_engine):
    record_spy = Spy()
    monkeypatch.setattr(vr, "record_until", record_spy)
    rem = make_reminder(due_in_s=0.0, sensitive=True)
    watch = FakeWatch(connected=False)
    status = vr.deliver_due_reminder(rem, watch, None, None, None, None,
                                     poll_s=0.05, record_s=1.0)
    assert status is None
    assert not record_spy.called
    assert not quiet_voice_engine["spoken"].called


def test_audio_failure_never_discloses_aloud(monkeypatch, quiet_voice_engine):
    def broken_mic(*a, **k):
        raise RuntimeError("PortAudio device lost")

    monkeypatch.setattr(vr, "record_until", broken_mic)
    rem = make_reminder(due_in_s=0.0, sensitive=True)
    watch = FakeWatch(connected=True)
    with pytest.raises(RuntimeError):
        vr.deliver_due_reminder(rem, watch, None, None, None, None,
                                poll_s=0.05, record_s=1.0)
    # The failure propagates to the bounded-retry loop; nothing was spoken.
    assert not quiet_voice_engine["spoken"].called
    assert not quiet_voice_engine["withheld"].called
