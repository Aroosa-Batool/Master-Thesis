#!/bin/zsh
set -u

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was not found. Run 'setup.command' first (double-click it)."
  echo
  read "?Press Return to close..."
  exit 1
fi

echo "Starting the Thesis Presentation Workstation..."
exec uv run python -m robot.apps.presentation_ui --port 0
