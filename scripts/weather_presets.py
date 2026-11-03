"""Visual sky states. They do not change the MMG wind, current, or wave inputs.

Clear, cloudy, and rain are exposure, cloud, fog, and rain-overlay values.
The four seasonal presets remain the only physical sea states.
"""

import math

PHYSICAL_FIELDS = ("wind_ms", "wind_deg", "current_ms", "current_deg", "wave_m", "wave_deg")

SEASONS = {
    "summer calm": {"wind_ms": 4.0, "wind_deg": 30.0, "current_ms": 0.25, "current_deg": 40.0, "wave_m": 0.4, "wave_deg": 30.0, "hour": 13.0, "lux": 12.0, "exposure": 0.25},
    "spring tide": {"wind_ms": 8.0, "wind_deg": 110.0, "current_ms": 1.40, "current_deg": 120.0, "wave_m": 1.3, "wave_deg": 110.0, "hour": 9.0, "lux": 9.0, "exposure": 0.05},
    "autumn gale": {"wind_ms": 18.0, "wind_deg": 200.0, "current_ms": 0.70, "current_deg": 190.0, "wave_m": 2.8, "wave_deg": 200.0, "hour": 16.0, "lux": 5.0, "exposure": -0.35},
    "winter storm": {"wind_ms": 22.0, "wind_deg": 210.0, "current_ms": 1.20, "current_deg": 130.0, "wave_m": 4.0, "wave_deg": 200.0, "hour": 20.5, "lux": 1.2, "exposure": -1.05},
}

ATMOSPHERES = {
    "clear": {"cloud": 0.08, "exposure_add": 0.15, "sky_mul": 1.05, "fog": 0.0, "rain": 0.0},
    "cloudy": {"cloud": 0.62, "exposure_add": -0.25, "sky_mul": 0.72, "fog": 0.004, "rain": 0.0},
    "rain": {"cloud": 0.88, "exposure_add": -0.55, "sky_mul": 0.48, "fog": 0.012, "rain": 1.0},
}


def apply_atmosphere(physical, name):
    if name not in ATMOSPHERES:
        raise ValueError("unknown visual atmosphere: %s" % name)
    if not all(math.isfinite(physical[field]) for field in PHYSICAL_FIELDS):
        raise ValueError("physical sea state must be finite")
    combined = {field: physical[field] for field in PHYSICAL_FIELDS}
    combined.update(ATMOSPHERES[name])
    combined["atmosphere"] = name
    return combined
