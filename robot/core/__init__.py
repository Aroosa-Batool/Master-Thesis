"""Domain logic and shared runtime.

  - ``paths``       - centralised on-disk locations for state + models
  - ``reminders``   - time-based reminder store
  - ``sensitivity`` - local AI classifier: is a reminder sensitive?
  - ``policy``      - Bangle.js BLE client + consent memory store
  - ``owner``       - enrolled-owner template store (face or voice)
  - ``robot_io``    - Ohbot glue + reminder speech + averaged bystander id
"""
