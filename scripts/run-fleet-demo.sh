#!/usr/bin/env bash
# Windowed fleet run. The camera follows the container ship while the tanker and bulker sail beside it.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/logs"
exec "$ROOT/scripts/launch-editor.sh" \
  "/Engine/Maps/Templates/TimeOfDay_Default?game=/Script/MaritimeFuelEfficiency.MaritimeGameMode" \
  -game -windowed -ResX=1024 -ResY=768 -WinX=0 -WinY=0 -nosound -log \
  -abslog="$ROOT/logs/fleet_demo.log" \
  "$@"
