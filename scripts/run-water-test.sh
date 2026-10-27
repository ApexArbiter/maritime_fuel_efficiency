#!/usr/bin/env bash
set -euo pipefail
ENGINE="/home/user/UnrealEngine/UE_5.8.4/Engine/Binaries/Linux/UnrealEditor"
PROJECT="/home/user/Projects/maritime_fuel_efficiency/MaritimeFuelEfficiency.uproject"
LOG="/home/user/Projects/maritime_fuel_efficiency/logs/ue_water_test.log"
mkdir -p "$(dirname "$LOG")"
exec "$ENGINE" "$PROJECT" "/Engine/Maps/Templates/TimeOfDay_Default?game=/Script/MaritimeFuelEfficiency.MaritimeGameMode" \
  -game -nullrhi -nosound -unattended -log -WaterTest \
  -abslog="$LOG" "$@"
