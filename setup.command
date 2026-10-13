#!/bin/zsh
# One-time setup for a new Mac: double-click this file (or run ./setup.command).
# Installs uv, Python 3.13 and the exact tested package versions (uv.lock),
# then downloads the models so the first session doesn't wait on the network.
set -u

SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1

finish() {
  echo
  read "?Press Return to close..."
  exit "$1"
}

echo "== 1/3  uv =="
if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh || { echo "Could not install uv."; finish 1; }
  export PATH="$HOME/.local/bin:$PATH"
fi
uv --version

echo
echo "== 2/3  Python + packages (a few GB on the first run) =="
uv sync || { echo "Package install failed."; finish 1; }

echo
echo "== 3/3  Models =="
uv run python -m robot.apps.download_models || { echo "Model download failed (check the internet connection)."; finish 1; }

echo
if ! command -v espeak >/dev/null 2>&1; then
  echo "NOTE: espeak is not installed. The robot needs it to speak:"
  echo "  brew install espeak"
  echo
fi

echo "Setup complete. Start the app with 'Start Thesis UI.command'."
finish 0
