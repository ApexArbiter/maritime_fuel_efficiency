"""Proportional helm used only as a test reference.

It reads the routing observation. It is not the model architecture another
person is preparing, and it is not a claim of voyage planning.

Observation index 4 is heading error in radians divided by pi. Multiplying
that by 2.5 commands about 10 degrees of rudder for a 19 degree error. At
the measured calm surge near 4.5 m/s the Nomoto time constant is on the
order of 150 s, so that rudder does not develop a turn before a waypoint a
few hundred metres ahead has been passed. Full rudder is now commanded at
20 degrees of heading error. Ordered speed still falls as the error grows.
"""

import math


# A 20 degree heading error saturates the +/- 35 degree rudder.
FULL_RUDDER_AT_DEG = 20.0

CALM_SEA = {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}
BREEZE_SEA = {"wind_ms": 8.0, "wind_deg": 90.0, "current_ms": 0.6, "current_deg": 90.0, "wave_m": 0.4, "wave_deg": 90.0}


def baseline_action(observation):
    """Rudder follows heading error. Ordered speed falls as the error grows."""
    heading_error = float(observation[4])
    rudder = max(-1.0, min(1.0, heading_error * (180.0 / FULL_RUDDER_AT_DEG)))
    speed = max(-1.0, min(1.0, 1.0 - 1.6 * abs(heading_error)))
    return (rudder, speed)


def realistic_scenarios():
    """Horizons set from the measured calm surge, not from a wished-for speed.

    Full ahead in calm is about 4.5 m/s at the first second and about 5.3 m/s
    at 60 s. Closing 250 m at 4.5 m/s takes about 56 s, so a 400 m destination
    (150 m arrival radius) is given 90 s. A 2500 m destination in 40 s can
    close only about 190 m, so that case is expected to truncate.
    """
    return (
        ("straight_400", (400.0, 0.0), 0.0, 90, CALM_SEA, "arrived"),
        ("heading_30", (600.0, 200.0), 30.0, 160, CALM_SEA, "arrived"),
        ("heading_minus_40", (500.0, -250.0), -40.0, 160, CALM_SEA, "arrived"),
        ("heading_50_close", (500.0, 300.0), 50.0, 160, CALM_SEA, "arrived"),
        ("beam_disturbance", (500.0, 0.0), 0.0, 140, BREEZE_SEA, "arrived"),
        ("short_horizon_2500", (2500.0, 0.0), 0.0, 40, CALM_SEA, "truncated"),
        ("unreachable_time", (8000.0, 0.0), 0.0, 8, CALM_SEA, "truncated"),
    )


def run_baseline(env, max_steps=None):
    return run_from_reset(env, options={"heading_deg": 0.0}, max_steps=max_steps)


def run_from_reset(env, seed=None, options=None, max_steps=None):
    observation, info = env.reset(seed=seed, options=options)
    limit = env.max_steps if max_steps is None else max_steps
    return _roll(env, observation, info, limit)


def _roll(env, observation, info, limit):
    start = info["distance_m"]
    progress = 0.0
    route = 0.0
    fuel_t = 0.0
    deviation = 0.0
    steps = 0
    reason = "running"
    while steps < limit:
        observation, reward, terminated, truncated, info = env.step(baseline_action(observation))
        progress += info["progress_m"]
        route += info["route_m"]
        fuel_t += info["fuel_t"]
        deviation = max(deviation, abs(info["cross_track_m"]))
        steps += 1
        reason = info["termination"]
        if terminated or truncated:
            break
    return {
        "start_distance_m": start,
        "final_distance_m": info["distance_m"],
        "progress_m": progress,
        "route_m": route,
        "max_cross_track_m": deviation,
        "fuel_t": fuel_t,
        "steps": steps,
        "duration_s": steps * env.step_s,
        "termination": reason,
        "final_x_m": info["x_m"],
        "final_y_m": info["y_m"],
        "final_heading_deg": info["heading_deg"],
    }
