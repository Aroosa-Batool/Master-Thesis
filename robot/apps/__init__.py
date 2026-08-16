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

A fifth and sixth app FUSE both sensors into one pipeline instead of picking a
modality: a due sensitive reminder wakes up ~5 min early, confirms the owner is
present, listens on the mic for the whole window, and opens the camera to look
around ONLY if the mic heard nobody but the owner - revealing the reminder aloud
only when neither sensor found a bystander. Same 2x1 consent-memory split:

    python -m robot.apps.fusion_remember     # mic->camera, cache-memory policy
    python -m robot.apps.fusion_reask        # mic->camera, re-consent policy

THE UNIFIED APP - the primary interactive entry point. It asks two startup
questions BEFORE loading any model or touching any hardware - (1) remember
disclosure decisions? yes -> cache-memory / no -> re-consent; (2) sensors?
1 -> microphone only / 2 -> mic first, camera only if no bystander voice was
heard - and then runs the matching engine above (the four combinations are
exactly {mic,fused} x {remember,reask}):

    python -m robot.apps.reminder_app
    python -m robot.apps.reminder_app --policy remember --sensors mic
    python -m robot.apps.reminder_app --policy reask --sensors both \
        --monitor-lead 420 --listen-duration 300

Its timing differs from the legacy single --lead: it wakes at T-420s (7 min);
for a sensitive reminder the mic records continuously for 300s (5 min), so it
closes at ~T-120s; the audio is analysed right then (and never retained), the
camera fallback (both-sensor mode only) is scheduled to finish close to T, and
delivery/consent happen at T. It also runs the fused engine fail-safe: an
inconclusive camera check withholds a sensitive reminder to the wrist instead
of ever counting as "owner alone". The two answers are never persisted; only
questions not answered by CLI flags are asked.

Setup / one-off:
    python -m robot.apps.add_reminder        # add a reminder by voice
    python -m robot.apps.enroll_face         # one-time owner face enrollment
    python -m robot.apps.enroll_voice        # one-time owner voice enrollment
    python -m robot.apps.list_cameras        # which camera the camera apps use

The two mic apps are thin wrappers over the shared engine
``robot.core.voice_reminder`` (differing only by ``remember=True/False``), the
two fusion apps are the same over ``robot.core.fusion_reminder``, and
``reminder_app`` drives those same two engines through their ``run_config``
entry points (``VoiceReminderConfig`` / ``FusionReminderConfig``).
"""
