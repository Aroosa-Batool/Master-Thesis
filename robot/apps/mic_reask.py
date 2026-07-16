"""Voice reminder delivery - RE-ASKS every time (never remembers consent).

The re-consent baseline: when a sensitive reminder is due and a bystander is
present (heard on the mic), the watch is asked EVERY time - even if the same
person answered a moment ago for an earlier reminder. No consent decision is ever
stored; the bystander is still recognised, but only for logging.

This is the mic analog of ``robot.apps.camera_reask`` and the control arm of the
study (against which ``mic_remember`` is compared). A thin wrapper over the shared
engine ``robot.core.voice_reminder``.

Run:
    python -m robot.apps.mic_reask
    NO_OHBOT=1 python -m robot.apps.mic_reask         # OS voice, no robot
"""

from robot.core.voice_reminder import run
from robot.core.logsetup import setup_logging

if __name__ == "__main__":
    setup_logging(run_name="mic_reask")
    run(remember=False)
