#!/bin/bash
# cortex_trigger.sh — thin wrapper around cortex_trigger.py for cron/CI use.
#
# Add to crontab (runs daily at 06:00):
#   0 6 * * * bash ~/repos/Cortex/scripts/cortex_trigger.sh >> ~/.cortex/trigger.log 2>&1
#
# Flags are passed through to cortex_trigger.py, e.g.:
#   bash cortex_trigger.sh --dry-run
#   bash cortex_trigger.sh --retry-failed --verbose

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$HOME/.cortex"
LOG_FILE="$LOG_DIR/trigger.log"

mkdir -p "$LOG_DIR"

echo "=== Cortex trigger started at $(date) ===" >> "$LOG_FILE"

python3 "$SCRIPT_DIR/cortex_trigger.py" "$@" 2>&1 | tee -a "$LOG_FILE"

echo "=== Cortex trigger finished at $(date) ===" >> "$LOG_FILE"
