#!/usr/bin/env bash
# Launch the maritime project on the local Unreal Engine 5.8 install.
# Uses the NVIDIA Vulkan driver when it initializes. If the loaded kernel
# module does not match the installed libraries, start on the CPU renderer.
set -euo pipefail

ENGINE="/home/user/UnrealEngine/UE_5.8.4"
EDITOR="${ENGINE}/Engine/Binaries/Linux/UnrealEditor"
PROJECT="/home/user/Projects/maritime_fuel_efficiency/MaritimeFuelEfficiency.uproject"

if [[ ! -x "$EDITOR" ]]; then
  echo "Unreal Editor is not installed at ${EDITOR}" >&2
  exit 1
fi

if nvidia-smi >/dev/null 2>&1; then
  export VK_DRIVER_FILES="/usr/share/vulkan/icd.d/nvidia_icd.json"
  export __GLX_VENDOR_LIBRARY_NAME="nvidia"
else
  # The loaded kernel module does not match the installed libraries, so the
  # NVIDIA Vulkan driver cannot create a device. llvmpipe can open the editor
  # only with software rendering and without Nanite or hardware ray tracing.
  unset VK_DRIVER_FILES || true
  unset __GLX_VENDOR_LIBRARY_NAME || true
  set -- -SkipVulkanProfileCheck -AllowSoftwareRendering -noraytracing \
    '-ini:Engine:[/Script/Engine.RendererSettings]:r.Nanite.ProjectEnabled=False,[SystemSettings]:r.Nanite=0,r.RayTracing=0,r.Lumen.HardwareRayTracing=0,r.Shadow.Virtual.Enable=0' \
    "$@"
fi
unset VK_ICD_FILENAMES || true

exec "$EDITOR" "$PROJECT" "$@"
