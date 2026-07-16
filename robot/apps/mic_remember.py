"""Voice reminder delivery - REMEMBERS each bystander's consent decision.

The cache-memory condition: when a sensitive reminder is due and a bystander is
present (heard on the mic), the watch is asked once per bystander and the Yes/No
is stored (``consent_cache_voice.json``) and reused the next time that same voice
is heard - so the owner is never re-asked about the same person.

This is the mic analog of ``robot.apps.camera_remember`` and the "remembers their
privacy preferences" arm of the study. A thin wrapper over the shared engine
``robot.core.voice_reminder``.

Run:
    python -m robot.apps.mic_remember
    NO_OHBOT=1 python -m robot.apps.mic_remember      # OS voice, no robot
"""

from robot.core.voice_reminder import run
from robot.core.logsetup import setup_logging

if __name__ == "__main__":
    setup_logging(run_name="mic_remember")
    run(remember=True)
