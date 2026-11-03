#!/usr/bin/env python3
"""One deterministic routing episode, plus the baseline helm cases.

The 12-step smoke policy from the completion report is not a navigator.
This script records why its progress was exactly zero, then records the
kinematic correction and a proportional helm.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import baseline_helm
import mmg_env
import mmg_physics as mmg
import sac_agent

CALM = {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}
BREEZE = {"wind_ms": 8.0, "wind_deg": 90.0, "current_ms": 0.6, "current_deg": 90.0, "wave_m": 0.4, "wave_deg": 90.0}


def episode(env, action_fn, limit):
    observation, info = env.reset(seed=5, options={"heading_deg": 0.0})
    rows = []
    rows.append("reset distance_m=%.3f x_m=%.3f y_m=%.3f heading_deg=%.3f" % (
        info["distance_m"], 0.0, 0.0, 0.0))
    for step in range(limit):
        action = np.asarray(action_fn(observation), dtype=np.float64)
        observation, reward, terminated, truncated, info = env.step(action)
        rows.append(
            "step %d action=%.3f,%.3f rudder_deg=%.2f ordered_ms=%.3f surge_ms=%.3f "
            "x_m=%.3f y_m=%.3f heading_deg=%.2f heading_error_rad=%.4f distance_m=%.3f "
            "progress_m=%.3f cross_m=%.3f route_m=%.3f reward=%.4f parts=%.4f,%.4f,%.4f "
            "fuel_t=%.6f termination=%s" % (
                step + 1, action[0], action[1], info["rudder_deg"], info["ordered_speed_ms"], info["surge_ms"],
                info["x_m"], info["y_m"], info["heading_deg"], info["heading_error_rad"], info["distance_m"],
                info["progress_m"], info["cross_track_m"], info["route_m"], reward,
                info["progress_reward"], info["deviation_reward"], info["effort_reward"],
                info["fuel_t"], info["termination"],
            )
        )
        if terminated or truncated:
            break
    return rows


def main(path):
    lines = []
    ship = mmg_env.reference_ship()
    clock = {"time": 0.0, "wind_cms": 0.0, "wind_deg": 0.0, "current_cms": 0.0, "current_deg": 0.0, "wave_cm": 0.0, "wave_deg": 0.0}
    returned, _, _, _, _ = mmg.integrate(ship, clock, 1.0)
    lines.append("CAUSE integrate keeps x_cm %.3f -> %.3f and y_cm %.3f -> %.3f" % (ship[16], returned[16], ship[17], returned[17]))
    lines.append("CAUSE fleet ApplyMotion and test_turning_circle.step_track add surge and sway after integrate")
    lines.append("CAUSE the routing env previously used that unchanged position, so distance and progress stayed 0")
    lines.append("CAUSE the smoke evaluation effort was 0.438, so the actions were not zero; the position was")
    lines.append("")
    ahead = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=4, sea=CALM)
    lines.append("FULL AHEAD after the kinematic update")
    lines.extend(episode(ahead, lambda _obs: (0.0, 1.0), 4))
    lines.append("")
    env = mmg_env.MaritimeRoutingEnv(destination_m=(6000.0, 800.0), step_s=0.2, max_steps=8)
    agent, updates = sac_agent.train_smoke(env, max_steps=12, seed=5)
    report = sac_agent.evaluate_policy(env, agent, episodes=1, max_steps=4, seed=5)
    lines.append("UNTRAINED SMOKE updates=%d reward=%.6f progress_m=%.6f effort=%.6f failures=%d arrived=%d" % (
        updates, report["mean_reward"], report["mean_progress_m"], report["mean_effort"], report["failures"], report["arrived"]))
    lines.append("UNTRAINED SMOKE is not a navigator")
    lines.append("")
    surge_env = mmg_env.MaritimeRoutingEnv(destination_m=(8000.0, 0.0), step_s=1.0, max_steps=180, sea=CALM)
    surge_env.reset(options={"heading_deg": 0.0})
    samples = {}
    for second in range(1, 181):
        _, _, _, _, info = surge_env.step((0.0, 1.0))
        if second in (1, 60, 180):
            samples[second] = info["surge_ms"]
    lines.append(
        "SURGE calm full ahead t=1s %.3f m/s, t=60s %.3f m/s, t=180s %.3f m/s, service %.2f m/s" % (
            samples[1], samples[60], samples[180], mmg_env.reference_ship()[15] / 100.0,
        )
    )
    lines.append("WHY a 2500 m leg in 40 s truncates: closure to the 150 m radius is 2350 m, and the measured 40 s progress is about 190 m")
    lines.append("WHY heading 50 deg toward (500, 300) missed under the old gain: observation error is radians/pi, so gain 2.5 commanded about 10 deg of rudder while the Nomoto lag at 4.5 m/s is about 150 s")
    lines.append("HELM full rudder is now commanded at 20 deg of heading error. Ordered speed is unchanged. Reward weights are unchanged.")
    counted = []
    real_advance = mmg_env.advance_position

    def counting(ship, dt):
        counted.append(dt)
        return real_advance(ship, dt)

    mmg_env.advance_position = counting
    try:
        once = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=2, sea=CALM)
        once.reset(options={"heading_deg": 0.0})
        once.step((0.0, 1.0))
    finally:
        mmg_env.advance_position = real_advance
    lines.append("POSITION advances %d times per 1 s step at %.2f s, which is one kinematic update per inner step" % (len(counted), counted[0] if counted else 0.0))
    lines.append("")
    cases = (
        ("straight calm", mmg_env.MaritimeRoutingEnv(destination_m=(2500.0, 0.0), step_s=1.0, max_steps=40, sea=CALM), {"heading_deg": 0.0}),
        ("offset heading", mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 1500.0), step_s=1.0, max_steps=80, sea=CALM), {"heading_deg": 50.0}),
        ("beam wind and current", mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=30, sea=BREEZE), {"heading_deg": 0.0}),
        ("time limit", mmg_env.MaritimeRoutingEnv(destination_m=(8000.0, 0.0), step_s=1.0, max_steps=3, sea=CALM), {"heading_deg": 0.0}),
    )
    for name, destination, heading, steps, sea, _expected in baseline_helm.realistic_scenarios():
        case_env = mmg_env.MaritimeRoutingEnv(destination_m=destination, step_s=1.0, max_steps=steps, sea=sea)
        result = baseline_helm.run_from_reset(case_env, options={"heading_deg": heading})
        lines.append(
            "HORIZON %s start_m=%.1f final_m=%.1f progress_m=%.1f route_m=%.1f cross_m=%.1f fuel_t=%.5f duration_s=%.0f heading_deg=%.1f %s" % (
                name, result["start_distance_m"], result["final_distance_m"], result["progress_m"], result["route_m"],
                result["max_cross_track_m"], result["fuel_t"], result["duration_s"], result["final_heading_deg"], result["termination"],
            )
        )
    for name, case_env, options in cases:
        result = baseline_helm.run_from_reset(case_env, options=options)
        lines.append(
            "BASELINE %s start_m=%.1f final_m=%.1f progress_m=%.1f route_m=%.1f cross_m=%.1f fuel_t=%.5f duration_s=%.0f %s" % (
                name, result["start_distance_m"], result["final_distance_m"], result["progress_m"], result["route_m"],
                result["max_cross_track_m"], result["fuel_t"], result["duration_s"], result["termination"],
            )
        )
    text = "\n".join(lines) + "\n"
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
