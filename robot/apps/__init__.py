"""Runnable entry points. Launch with ``python -m robot.apps.<name>``.

The four delivery apps form a 2x2 of sensing modality x consent-memory policy
(the study conditions): whether a bystander's Yes/No is REMEMBERED across
encounters, or the watch is RE-ASKED every time.

                 remembers preference        re-asks every time
    camera       camera_remember             camera_reask
    mic          mic_remember                mic_reask

    python -m robot.apps.mic_remember        # voice, cache-memory policy
    python -m robot.apps.mic_reask           # voice, re-consent policy
    python -m robot.apps.camera_remember     # camera, cache-memory policy
    python -m robot.apps.camera_reask        # camera, re-consent policy

Setup / one-off:
    python -m robot.apps.add_reminder        # add a reminder by voice
    python -m robot.apps.enroll_face         # one-time owner face enrollment
    python -m robot.apps.enroll_voice        # one-time owner voice enrollment

The two mic apps are thin wrappers over the shared engine
``robot.core.voice_reminder`` (differing only by ``remember=True/False``).
"""
