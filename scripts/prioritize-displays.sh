#!/usr/bin/env bash
# Keep the virtual display stack off the cores and memory Unreal is allowed to use.
# Selkies, x0vnc, and guacd are the remote displays. KWin and Plasma composite them.
# Xorg and SDDM run as root, so they stay where the system put them.
set -u

USER_ID="$(id -u)"
APP="/sys/fs/cgroup/user.slice/user-${USER_ID}.slice/user@${USER_ID}.service/app.slice"
CORES="$(nproc)"

if (( CORES > 2 )); then
  DISPLAY_CPUS="0,1"
else
  DISPLAY_CPUS="0"
fi

pin_pid() {
  local pid="$1"
  [[ -d "/proc/${pid}" ]] || return 0
  taskset -cp "$DISPLAY_CPUS" "$pid" >/dev/null 2>&1 || true
}

pin_cgroup() {
  local dir="$1"
  [[ -r "${dir}/cgroup.procs" ]] || return 0
  local pid
  while read -r pid; do
    pin_pid "$pid"
  done < "${dir}/cgroup.procs"
}

protect_memory() {
  local dir="$1"
  local min_bytes="$2"
  local low_bytes="$3"
  [[ -d "$dir" ]] || return 0
  echo "$min_bytes" > "${dir}/memory.min" 2>/dev/null || true
  echo "$low_bytes" > "${dir}/memory.low" 2>/dev/null || true
}

pin_cgroup "${APP}/selkies.service"
pin_cgroup "${APP}/x0vnc.service"
pin_cgroup "${APP}/guacd.service"

# 1 GiB held for the Selkies encoder, 256 MiB for each extra display server.
protect_memory "${APP}/selkies.service" 1073741824 2147483648
protect_memory "${APP}/x0vnc.service" 268435456 536870912
protect_memory "${APP}/guacd.service" 268435456 536870912

for pid in $(pgrep -x kwin_x11 || true) $(pgrep -x plasmashell || true); do
  pin_pid "$pid"
done

echo "Virtual displays pinned to CPU ${DISPLAY_CPUS}. Unreal is limited to the remaining cores." >&2
