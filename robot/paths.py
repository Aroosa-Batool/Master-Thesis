"""Centralised on-disk locations for runtime state and downloaded models.

Every entry point resolves these same paths (rather than paths relative to its
own module file), so the camera apps and the voice runner share ONE reminder
list, ONE owner enrollment, ONE bystander gallery, and ONE consent cache per
modality. All of it is user data or auto-downloaded weights - gitignored, never
source. Directories are created on first write by the stores/model downloader.

This lives at the package top level (``robot.paths``) because it is foundational
config depended on by every layer - apps, core, and perception alike.
"""

from pathlib import Path

# This file is robot/paths.py, so its parent is the robot/ package root.
STATE_DIR = Path(__file__).resolve().parent / "state"
MODELS_DIR = STATE_DIR / "models"          # YuNet + SFace ONNX (auto-downloaded)
LOGS_DIR = STATE_DIR / "logs"              # per-run structured CSV logs (robot.core.logsetup)

# Shared across modalities
REMINDERS_PATH = STATE_DIR / "reminders.json"

# Camera modality
CONSENT_CACHE_PATH = STATE_DIR / "consent_cache.json"
FACE_DB_PATH = STATE_DIR / "face_db.json"
OWNER_FACE_PATH = STATE_DIR / "owner_face.json"

# Voice modality
VOICE_CONSENT_CACHE_PATH = STATE_DIR / "consent_cache_voice.json"
VOICE_DB_PATH = STATE_DIR / "voice_db.json"
OWNER_VOICE_PATH = STATE_DIR / "owner_voice.json"
