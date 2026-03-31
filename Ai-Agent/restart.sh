#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Stop all currently running bot.py processes to avoid Telegram getUpdates conflict.
pids="$(pgrep -f "[Pp]ython.*bot.py|$SCRIPT_DIR/.+bot.py|/bot.py" || true)"
if [[ -n "$pids" ]]; then
  echo "Stopping old bot processes: $pids"
  kill $pids || true
  sleep 1
fi

remaining="$(pgrep -f "[Pp]ython.*bot.py|$SCRIPT_DIR/.+bot.py|/bot.py" || true)"
if [[ -n "$remaining" ]]; then
  echo "Force stopping remaining processes: $remaining"
  kill -9 $remaining || true
fi

echo "Starting bot..."
exec "$SCRIPT_DIR/run.sh"
