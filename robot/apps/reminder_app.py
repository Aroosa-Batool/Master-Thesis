"""Unified interactive reminder application - ONE entry point, four conditions.

Run:
    python -m robot.apps.reminder_app

Before anything heavy happens - no model is loaded, no microphone/camera device
is touched, no BLE scan starts - the app asks two configuration questions:

1. "Should I remember your disclosure decisions for recognized bystanders?"
   - yes -> the existing cache-memory policy (a bystander's explicit Yes/No
     watch answer is stored and reused);
   - no  -> the existing re-consent policy (the watch is asked on every
     applicable reminder; nothing is ever stored).
   This governs ONLY the reuse of explicit Yes/No watch answers. It does not
   store raw audio, video, reminder configuration, or unanswered prompts.

2. "Which sensors should I use?"
   - 1 -> microphone only (the voice engine, ``robot.core.voice_reminder``);
   - 2 -> microphone first, then camera if no bystander voice is detected
     (the fused engine, ``robot.core.fusion_reminder``). The two sensors are
     never open simultaneously: the camera opens only for a brief head scan,
     after the mic window closed without hearing a non-owner voice.

Both questions can be answered ahead of time with CLI flags (``--policy``,
``--sensors``); only the ones NOT supplied are asked interactively. Ctrl-C or
EOF during the questions exits cleanly without initialising any hardware. The
two answers are never persisted - the next interactive run asks again.

Timing (defaults; override with ``--monitor-lead`` / ``--listen-duration``):
for a reminder scheduled at time T, the app wakes at T-420s (7 min). For a
SENSITIVE reminder the mic then records continuously for 300s (5 min), so it
stops at ~T-120s (2 min); the recording is analysed right after the mic closes
and is never retained. In both-sensor mode a mic miss triggers the head-mounted
camera scan, scheduled late in the remaining interval so the freshest practical
look at the room finishes close to T. Delivery (and any watch consent prompt)
happens at T, never early.

The four combinations map onto the EXISTING engines - this launcher adds no new
sensing, consent, or delivery logic:

    remember + mic  -> voice engine with its ConsentStore  (mic_remember's policy)
    reask    + mic  -> voice engine without a ConsentStore (mic_reask's policy)
    remember + both -> fused engine with its fusion cache  (fusion_remember's)
    reask    + both -> fused engine without a ConsentStore (fusion_reask's)

Unlike the legacy fusion apps, this app runs the fused engine in fail-safe
mode: an inconclusive camera check (failed open, no usable frame, failed scan
or identification) withholds a sensitive reminder and delivers it privately to
the wrist - it is never interpreted as "the owner is alone".
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

# Deliberately NO robot/core imports at module level (beyond the trivial path
# constants): the engines pull in torch, OpenCV, sounddevice, the Ohbot SDK and
# bleak, and the contract of this app is that nothing heavy happens until BOTH
# questions are answered. The engine modules are imported inside _launch().
from robot.paths import FUSION_CONSENT_CACHE_PATH, VOICE_CONSENT_CACHE_PATH

POLICY_REMEMBER = "remember"
POLICY_REASK = "reask"
SENSORS_MIC = "mic"
SENSORS_BOTH = "both"

# T-7min wake-up, 5-min recording -> the mic runs T-7min..T-2min by default.
DEFAULT_MONITOR_LEAD_S = 420.0
DEFAULT_LISTEN_DURATION_S = 300.0

QUESTION_POLICY = (
    "Should I remember your disclosure decisions for recognized bystanders?\n"
    "[yes/no] > "
)
QUESTION_SENSORS = (
    "Which sensors should I use?\n"
    "  1. Microphone only\n"
    "  2. Microphone first, then camera if no bystander voice is detected\n"
    "[1/2] > "
)

# Accepted spellings for each answer, lower-cased. Anything else re-prompts.
_POLICY_ANSWERS = {
    "yes": POLICY_REMEMBER, "y": POLICY_REMEMBER, "remember": POLICY_REMEMBER,
    "no": POLICY_REASK, "n": POLICY_REASK, "reask": POLICY_REASK,
}
_SENSOR_ANSWERS = {
    "1": SENSORS_MIC, "mic": SENSORS_MIC, "microphone": SENSORS_MIC,
    "2": SENSORS_BOTH, "both": SENSORS_BOTH,
}


@dataclass(frozen=True)
class AppConfig:
    """The four startup choices, resolved from CLI flags and/or the questions."""

    policy: str                # POLICY_REMEMBER | POLICY_REASK
    sensors: str               # SENSORS_MIC | SENSORS_BOTH
    monitor_lead_s: float = DEFAULT_MONITOR_LEAD_S
    listen_duration_s: float = DEFAULT_LISTEN_DURATION_S
    reminder_id: str | None = None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m robot.apps.reminder_app",
        description="Unified reminder delivery: asks two startup questions "
                    "(consent policy, sensors) and runs the matching existing "
                    "engine. Flags below answer a question ahead of time; only "
                    "unanswered questions are asked interactively.",
    )
    ap.add_argument("--policy", choices=(POLICY_REMEMBER, POLICY_REASK),
                    help="consent policy: 'remember' reuses a bystander's stored "
                         "Yes/No watch answers; 'reask' asks on every applicable "
                         "reminder and never stores decisions")
    ap.add_argument("--sensors", choices=(SENSORS_MIC, SENSORS_BOTH),
                    help="'mic' = microphone only; 'both' = microphone first, "
                         "then camera if no bystander voice is detected")
    ap.add_argument("--monitor-lead", type=float, default=DEFAULT_MONITOR_LEAD_S,
                    metavar="SECONDS",
                    help=f"wake up this many seconds before a reminder's time "
                         f"(default {DEFAULT_MONITOR_LEAD_S:g} = 7 min)")
    ap.add_argument("--listen-duration", type=float,
                    default=DEFAULT_LISTEN_DURATION_S, metavar="SECONDS",
                    help=f"for a sensitive reminder, record the mic continuously "
                         f"for this many seconds starting at the wake-up "
                         f"(default {DEFAULT_LISTEN_DURATION_S:g} = 5 min)")
    ap.add_argument("--reminder-id", default=None,
                    help="process only this pending reminder (used by the presentation UI)")
    return ap


def validate_timing(monitor_lead: float, listen_duration: float) -> None:
    """Reject timing values that cannot produce the documented T-7..T-2 window."""

    if monitor_lead <= 0:
        raise SystemExit("[reminder_app] --monitor-lead must be > 0 seconds.")
    if listen_duration <= 0:
        raise SystemExit("[reminder_app] --listen-duration must be > 0 seconds.")
    if listen_duration > monitor_lead:
        raise SystemExit(
            "[reminder_app] --listen-duration cannot exceed --monitor-lead: the "
            "mic would still be recording after the reminder's time. "
            f"(got listen={listen_duration:g}s > lead={monitor_lead:g}s)"
        )


def ask_choice(prompt: str, answers: dict[str, str], input_fn=input) -> str:
    """Ask until one of ``answers`` is given; EOF/Ctrl-C propagate to main()."""

    while True:
        raw = input_fn(prompt)
        choice = answers.get(raw.strip().lower())
        if choice is not None:
            return choice
        valid = "/".join(sorted(set(answers), key=len))
        print(f"Sorry, I did not understand {raw.strip()!r}. "
              f"Please answer one of: {valid}.", flush=True)


def build_config(args: argparse.Namespace, input_fn=input) -> AppConfig:
    """Resolve the four choices, asking only the questions the CLI left open."""

    validate_timing(args.monitor_lead, args.listen_duration)
    policy = args.policy or ask_choice(QUESTION_POLICY, _POLICY_ANSWERS, input_fn)
    sensors = args.sensors or ask_choice(QUESTION_SENSORS, _SENSOR_ANSWERS, input_fn)
    return AppConfig(
        policy=policy,
        sensors=sensors,
        monitor_lead_s=args.monitor_lead,
        listen_duration_s=args.listen_duration,
        reminder_id=args.reminder_id,
    )


def summary_lines(cfg: AppConfig) -> list[str]:
    """The concise configuration summary printed before anything starts."""

    lead = cfg.monitor_lead_s
    rec = cfg.listen_duration_s
    stop = lead - rec
    if cfg.policy == POLICY_REMEMBER:
        cache = (VOICE_CONSENT_CACHE_PATH if cfg.sensors == SENSORS_MIC
                 else FUSION_CONSENT_CACHE_PATH)
        policy_line = (f"remember - reuse each bystander's explicit Yes/No watch "
                       f"answer (stored in {cache})")
    else:
        policy_line = ("reask - ask on the watch every time; no consent decision "
                       "is ever stored")
    if cfg.sensors == SENSORS_MIC:
        sensors_line = ("microphone only (no face models are loaded; the camera "
                        "is never accessed)")
        fallback_line = ("a silent room counts as 'no audible bystander' "
                         "(voice-only limit)")
    else:
        sensors_line = ("microphone first, then camera - the head-mounted camera "
                        "opens only for a brief scan if the mic heard no "
                        "bystander voice; never both at once. A preview window "
                        "shows what the camera sees for exactly that scan and "
                        "closes with the device (CAMERA_PREVIEW=0 to hide it)")
        fallback_line = ("an inconclusive camera check withholds the reminder "
                         "(private note to the wrist) - it never counts as "
                         "'owner alone'")
    return [
        f"[config] consent policy   : {policy_line}",
        f"[config] sensors          : {sensors_line}",
        f"[config] timing           : wake at T-{lead:g}s; for a sensitive "
        f"reminder the mic records {rec:g}s (T-{lead:g}s -> T-{stop:g}s), the "
        f"audio is analysed as soon as the mic closes (and never retained), and "
        f"delivery/consent happen at T",
        f"[config] fallback         : {fallback_line}",
        "[config] these choices are not saved; the next interactive run asks "
        "again.",
    ]


def _launch(cfg: AppConfig) -> None:
    """Import the chosen engine (heavy) and run it. Nothing heavy before this."""

    from robot.core.logsetup import setup_logging

    setup_logging(run_name="reminder_app")
    remember = cfg.policy == POLICY_REMEMBER
    if cfg.sensors == SENSORS_MIC:
        # Mic-only: the voice engine never imports face models or the camera.
        from robot.core import voice_reminder

        voice_reminder.run_config(voice_reminder.VoiceReminderConfig(
            remember=remember,
            lead_s=cfg.monitor_lead_s,
            record_s=cfg.listen_duration_s,
            target_reminder_id=cfg.reminder_id,
        ))
    else:
        from robot.core import fusion_reminder

        fusion_reminder.run_config(fusion_reminder.FusionReminderConfig(
            remember=remember,
            lead_s=cfg.monitor_lead_s,
            record_s=cfg.listen_duration_s,
            # A sensor failure must never read as "the owner is alone".
            camera_fail_safe=True,
            target_reminder_id=cfg.reminder_id,
        ))


def main(argv: list[str] | None = None, input_fn=input) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = build_config(args, input_fn)
    except (EOFError, KeyboardInterrupt):
        # Clean exit BEFORE any hardware, model, or BLE initialisation.
        print("\n[reminder_app] cancelled - no hardware was initialised, no "
              "models were loaded.", flush=True)
        return 130
    for line in summary_lines(cfg):
        print(line, flush=True)
    from robot.core import presentation_telemetry as telemetry
    telemetry.stage(
        "configuration", "complete", f"{cfg.policy} policy; {cfg.sensors} sensors.",
        policy=cfg.policy, sensors=cfg.sensors, reminder_id=cfg.reminder_id,
    )
    _launch(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
