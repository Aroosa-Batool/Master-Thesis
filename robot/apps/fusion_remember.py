"""Fused reminder delivery (mic then camera) - REMEMBERS each bystander's consent.

The single pipeline that uses both sensors in priority order. When a sensitive
reminder is due it wakes up ~5 min early, confirms the owner is in the room (the
watch's BLE link), listens on the mic for the whole window, and - only if it
heard nobody but the owner - opens the camera and looks around to double-check.
If neither sensor found anyone, the sensitive information is revealed aloud.

The cache-memory condition: when a bystander IS found, the watch is asked once
per bystander and the Yes/No is stored (``consent_cache_fusion.json``) and reused
the next time that same person is found - so the owner is never re-asked about
them. The re-consent twin is ``robot.apps.fusion_reask``.

A thin wrapper over the shared engine ``robot.core.fusion_reminder``, which is
itself built from the unchanged single-modality pieces (``voice_reminder`` for
the mic window, ``head_scan`` + ``presence`` for the camera sweep, ``robot_io``
for the speech and consent behaviours).

Needs BOTH owner enrollments - voice (``enroll_voice``) and face
(``enroll_face``) - unless started with ``--no-camera``.

Run:
    python -m robot.apps.fusion_remember
    NO_OHBOT=1 python -m robot.apps.fusion_remember    # OS voice, no robot
    python -m robot.apps.fusion_remember --no-camera   # mic only (ablation)
"""

from robot.core.fusion_reminder import run
from robot.core.logsetup import setup_logging

if __name__ == "__main__":
    setup_logging(run_name="fusion_remember")
    run(remember=True)
