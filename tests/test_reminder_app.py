"""Startup behaviour of the unified ``robot.apps.reminder_app`` launcher.

Covers: the four policy x sensor combinations mapping onto the right engine
config, CLI flags bypassing exactly the questions they answer, invalid-answer
re-prompting, clean EOF/Ctrl-C exit before any hardware init, and the timing
defaults/validation (T-7 min wake, 5 min recording).
"""

from __future__ import annotations

import pytest

import robot.apps.reminder_app as app
from tests.conftest import Spy


def _fail_input(prompt=""):
    raise AssertionError("interactive question asked although the CLI answered it")


def _scripted(answers):
    """An input_fn yielding ``answers`` in order; fails if asked for more."""

    it = iter(answers)

    def input_fn(prompt=""):
        try:
            return next(it)
        except StopIteration:
            raise AssertionError("more questions asked than answers scripted")

    return input_fn


@pytest.fixture
def engines(monkeypatch):
    """Patch both engines' run_config (and logging setup) with spies."""

    import robot.core.fusion_reminder as fr
    import robot.core.logsetup as logsetup
    import robot.core.voice_reminder as vr

    spies = {"voice": Spy(), "fusion": Spy()}
    monkeypatch.setattr(vr, "run_config", spies["voice"])
    monkeypatch.setattr(fr, "run_config", spies["fusion"])
    monkeypatch.setattr(logsetup, "setup_logging", lambda **kwargs: None)
    return spies


@pytest.mark.parametrize("policy,sensors", [
    ("remember", "mic"), ("reask", "mic"),
    ("remember", "both"), ("reask", "both"),
])
def test_four_combinations_map_to_the_right_engine(engines, policy, sensors):
    rc = app.main(["--policy", policy, "--sensors", sensors],
                  input_fn=_fail_input)
    assert rc == 0
    if sensors == "mic":
        assert engines["voice"].called and not engines["fusion"].called
        cfg = engines["voice"].calls[0][0][0]
    else:
        assert engines["fusion"].called and not engines["voice"].called
        cfg = engines["fusion"].calls[0][0][0]
        # The unified app always runs the fused engine fail-safe: an
        # inconclusive camera check must never read as "owner alone".
        assert cfg.camera_fail_safe is True
    assert cfg.remember is (policy == "remember")
    # T-7 min wake-up, 5 min continuous recording - the defaults.
    assert cfg.lead_s == 420.0
    assert cfg.record_s == 300.0


def test_questions_fill_in_what_the_cli_left_open(engines):
    # --policy given -> only the sensors question is asked.
    rc = app.main(["--policy", "reask"], input_fn=_scripted(["2"]))
    assert rc == 0
    cfg = engines["fusion"].calls[0][0][0]
    assert cfg.remember is False


def test_fully_interactive_run_asks_both_questions(engines):
    rc = app.main([], input_fn=_scripted(["yes", "1"]))
    assert rc == 0
    cfg = engines["voice"].calls[0][0][0]
    assert cfg.remember is True


def test_invalid_answers_reprompt_until_valid(engines, capsys):
    rc = app.main([], input_fn=_scripted(["maybe", "", "no", "0", "camera", "1"]))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.count("did not understand") == 4
    cfg = engines["voice"].calls[0][0][0]
    assert cfg.remember is False


def test_eof_exits_cleanly_without_initialising_anything(engines, capsys):
    def eof(prompt=""):
        raise EOFError

    rc = app.main([], input_fn=eof)
    assert rc == 130
    assert not engines["voice"].called and not engines["fusion"].called
    assert "cancelled" in capsys.readouterr().out


def test_ctrl_c_exits_cleanly_without_initialising_anything(engines):
    def interrupt(prompt=""):
        raise KeyboardInterrupt

    rc = app.main([], input_fn=interrupt)
    assert rc == 130
    assert not engines["voice"].called and not engines["fusion"].called


def test_timing_flags_are_passed_through(engines):
    rc = app.main(["--policy", "remember", "--sensors", "mic",
                   "--monitor-lead", "100", "--listen-duration", "60"],
                  input_fn=_fail_input)
    assert rc == 0
    cfg = engines["voice"].calls[0][0][0]
    assert cfg.lead_s == 100.0
    assert cfg.record_s == 60.0


def test_target_reminder_is_passed_to_selected_engine(engines):
    rc = app.main([
        "--policy", "remember", "--sensors", "both",
        "--reminder-id", "rem_042",
    ], input_fn=_fail_input)
    assert rc == 0
    cfg = engines["fusion"].calls[0][0][0]
    assert cfg.target_reminder_id == "rem_042"


@pytest.mark.parametrize("lead,listen", [
    (0, 300), (-5, 300), (420, 0), (420, -1), (300, 301),
])
def test_bad_timing_is_rejected_before_any_question(engines, lead, listen):
    with pytest.raises(SystemExit):
        app.main(["--policy", "remember", "--sensors", "mic",
                  "--monitor-lead", str(lead), "--listen-duration", str(listen)],
                 input_fn=_fail_input)
    assert not engines["voice"].called and not engines["fusion"].called


def test_summary_mentions_the_timeline_and_non_persistence(engines, capsys):
    app.main(["--policy", "reask", "--sensors", "both"], input_fn=_fail_input)
    out = capsys.readouterr().out
    assert "T-420s -> T-120s" in out
    assert "not saved" in out
