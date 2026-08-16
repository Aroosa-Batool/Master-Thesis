"""Fused reminder delivery (mic then camera) - RE-ASKS every time, remembers nothing.

Same sensing pipeline as ``robot.apps.fusion_remember`` - wake ~5 min early,
confirm the owner is present via the watch, listen for the whole window, and open
the camera to look around only if the mic heard nobody but the owner - but the
disclosure decision is taken **fresh every time**. There is no consent cache:
every due reminder with a bystander present triggers a new Yes/No prompt on the
watch, even if the same person answered a moment ago.

This is the privacy "Re-Consent" baseline the fused cache-memory app is compared
against; the only difference is the absence of the stored-decision lookup. The
bystander is still **recognised** - ids are minted and logged via the shared
``voice_db.json`` / ``face_db.json`` galleries, and the owner is filtered out via
the owner enrollments - but that identity is used only for logging here; it never
short-circuits the prompt.

A thin wrapper over the shared engine ``robot.core.fusion_reminder``.

Needs BOTH owner enrollments - voice (``enroll_voice``) and face
(``enroll_face``) - unless started with ``--no-camera``.

Run:
    python -m robot.apps.fusion_reask
    NO_OHBOT=1 python -m robot.apps.fusion_reask       # OS voice, no robot
    python -m robot.apps.fusion_reask --no-camera      # mic only (ablation)
"""

from robot.core.fusion_reminder import run
from robot.core.logsetup import setup_logging

if __name__ == "__main__":
    setup_logging(run_name="fusion_reask")
    run(remember=False)
