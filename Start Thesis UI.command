#!/bin/zsh
set -u

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1

if [[ -x "$SCRIPT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3.13 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.13)"
else
  echo "Python 3.13 was not found."
  echo "Create the project environment first:"
  echo "  python3.13 -m venv .venv"
  echo "  .venv/bin/pip install -r requirements.txt"
  echo
  read "?Press Return to close..."
  exit 1
fi

echo "Starting the Thesis Presentation Workstation..."
exec "$PYTHON_BIN" -m robot.apps.presentation_ui --port 0
