"""Presence-aware, reminder-triggered social-robot prototype.

Layers:
  - ``robot.apps``       - runnable entry points (``python -m robot.apps.<name>``)
  - ``robot.core``       - domain logic: reminders, sensitivity, consent/BLE,
                           owner store, and the shared robot I/O runtime
  - ``robot.perception`` - sensing + identity: face (YuNet/SFace), voice
                           (Resemblyzer d-vectors), microphone device selection

Runtime state (galleries, consent caches, owner enrollments, reminders, and the
auto-downloaded face-model weights) lives under ``robot/state`` - see
``robot.paths``. It is user data, not source, and is gitignored.
"""
