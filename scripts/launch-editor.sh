#!/usr/bin/env bash
# Launch the maritime project on the local Unreal Engine 5.8 install.
# Virtual displays keep CPUs 0-1 and a protected memory floor.
# Unreal is confined to the remaining cores, a 16 GB soft / 24 GB hard memory cap,
# idle I/O priority, and a medium picture without Nanite, Lumen, or ray tracing.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="/home/user/UnrealEngine/UE_5.8.4"
EDITOR="${ENGINE}/Engine/Binaries/Linux/UnrealEditor"
PROJECT="${ROOT}/MaritimeFuelEfficiency.uproject"

if [[ ! -x "$EDITOR" ]]; then
  echo "Unreal Editor is not installed at ${EDITOR}" >&2
  exit 1
fi

"$ROOT/scripts/prioritize-displays.sh"

CORES="$(nproc)"
if (( CORES > 2 )); then
  UNREAL_CPUS="2-$((CORES - 1))"
else
  UNREAL_CPUS="0-$((CORES - 1))"
fi

if nvidia-smi >/dev/null 2>&1; then
  export VK_DRIVER_FILES="/usr/share/vulkan/icd.d/nvidia_icd.json"
  export __GLX_VENDOR_LIBRARY_NAME="nvidia"
else
  unset VK_DRIVER_FILES || true
  unset __GLX_VENDOR_LIBRARY_NAME || true
  set -- -SkipVulkanProfileCheck -AllowSoftwareRendering -noraytracing "$@"
fi
unset VK_ICD_FILENAMES || true

exec systemd-run --user --scope --collect \
  -p MemoryHigh=16G \
  -p MemoryMax=24G \
  -- \
  nice -n 19 ionice -c 3 taskset -c "$UNREAL_CPUS" \
  "$EDITOR" "$PROJECT" \
  "$@" \
  -ExecCmds="sg.ResolutionQuality 100, sg.ViewDistanceQuality 2, sg.AntiAliasingQuality 3, sg.ShadowQuality 2, sg.GlobalIlluminationQuality 1, sg.ReflectionQuality 2, sg.PostProcessQuality 2, sg.TextureQuality 2, sg.EffectsQuality 2, sg.FoliageQuality 0, sg.ShadingQuality 2, sg.LandscapeQuality 0, r.ScreenPercentage 100, r.AntiAliasingMethod 4, r.ReflectionMethod 2, r.DynamicGlobalIlluminationMethod 2, r.MotionBlurQuality 0, r.BloomQuality 4, r.AmbientOcclusionLevels 2, r.DepthOfFieldQuality 0, r.LensFlareQuality 0, r.LightShaftQuality 1, r.VolumetricFog 0, r.VolumetricCloud 0, r.SSR.Quality 2, r.SSGI.Quality 2, r.EyeAdaptationQuality 2, r.Tonemapper.Quality 5, r.Tonemapper.Sharpen 0.5"
