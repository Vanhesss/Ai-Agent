#!/usr/bin/env bash
set -euo pipefail

# Always run from the project directory where this script lives.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
elif [[ -x "venv/bin/python" ]]; then
  PYTHON_BIN="venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "Python not found. Install Python 3 or create .venv/venv first."
  exit 1
fi

echo "Using Python: $PYTHON_BIN"
exec "$PYTHON_BIN" bot.py
