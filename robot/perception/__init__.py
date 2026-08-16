"""Sensing and identity.

  - ``face_id``      - YuNet detection + SFace 128-D face embeddings
  - ``face_db``      - embedding gallery -> stable person IDs (faces AND voices)
  - ``voice_id``     - Resemblyzer 256-D speaker "d-vector" embeddings
  - ``speech_vad``    - is a sound a HUMAN VOICE at all? (Silero neural VAD)
  - ``audio_device``  - microphone input-device selection
  - ``camera_device`` - camera selection (prefers the head-mounted USB webcam)
  - ``presence``      - who is in view, across one frame or a whole head sweep

``voice_id`` answers "WHOSE voice is this?" and ``speech_vad`` answers "is this a
voice at all?". Both are needed: the speaker encoder will happily embed a coffee
grinder and hand back a stable id for it, and since that id is not the owner's,
the pipeline would file the grinder as a bystander. ``speech_vad`` runs first and
drops everything that is not speech.
"""
