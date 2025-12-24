#!/usr/bin/env bash
# Run the expiration notification generator. Intended for cron/systemd timers.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/myproject"

cd "$PROJECT_ROOT"

# Use your Python/venv path if needed; defaults to system python
python manage.py generate_expiration_notifications
