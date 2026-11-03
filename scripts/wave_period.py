"""Visual wave period, separate from the MMG wave height.

`mmg_physics.wave_surface` fixes the wavelength at 90 m and uses the
deep-water frequency `sqrt(g * k)`. That frequency is not an input, and this
module does not change it. A visual period only scales the drawn swell's
angular speed. It does not change `wave_cm`.
"""

import math

VISUAL_PERIOD_MIN_S = 4.0
VISUAL_PERIOD_MAX_S = 18.0
VISUAL_PERIOD_NOMINAL_S = 8.0


def physical_wave_period_s():
    """Period implied by the existing 90 m deep-water wave. Read-only."""
    wave_number = 2.0 * math.pi / 9000.0
    omega = math.sqrt(980.0 * wave_number)
    return (2.0 * math.pi) / omega


def clamp_visual_period(seconds):
    if not math.isfinite(seconds):
        raise ValueError("visual wave period must be finite")
    return min(VISUAL_PERIOD_MAX_S, max(VISUAL_PERIOD_MIN_S, float(seconds)))


def visual_omega_scale(seconds):
    """Multiplier on the drawn swell's angular speed. 8 s leaves it unchanged."""
    return VISUAL_PERIOD_NOMINAL_S / clamp_visual_period(seconds)


def with_visual_period(state, seconds):
    """Copy a physical sea state and attach a visual period. Wave height stays."""
    period = clamp_visual_period(seconds)
    copied = dict(state)
    copied["visual_period_s"] = period
    copied["visual_omega_scale"] = visual_omega_scale(period)
    return copied
