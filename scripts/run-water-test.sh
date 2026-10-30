#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG="${ROOT}/logs/ue_water_test.log"
mkdir -p "$(dirname "$LOG")"
exec "$ROOT/scripts/launch-editor.sh" \
  "/Engine/Maps/Templates/TimeOfDay_Default?game=/Script/MaritimeFuelEfficiency.MaritimeGameMode" \
  -game -nullrhi -nosound -unattended -log -WaterTest \
  -abslog="$LOG" "$@"
