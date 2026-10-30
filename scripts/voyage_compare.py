#!/usr/bin/env python3
"""Replay the fleet autopilot through the Python MMG model for calm and storm.

This uses the same step as the live UDP server. It does not replace that server.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import mmg_physics as mmg


SHIPS = {
    "Container ship": {
        "start": (0.0, 0.0),
        "waypoints": ((52000.0, 9000.0), (120000.0, 22000.0)),
        "length": 30000.0,
        "beam": 4280.0,
        "draft": 1450.0,
        "freeboard": 800.0,
        "mass": 145000.0 * 1000.0,
        "power": 45700000.0,
        "service_kn": 22.5,
    },
    "Aframax tanker": {
        "start": (-5000.0, 14000.0),
        "waypoints": ((48000.0, 24000.0), (116000.0, 38000.0)),
        "length": 24500.0,
        "beam": 4200.0,
        "draft": 1500.0,
        "freeboard": 600.0,
        "mass": 128000.0 * 1000.0,
        "power": 13500000.0,
        "service_kn": 15.0,
    },
    "Panamax bulker": {
        "start": (-9000.0, -14000.0),
        "waypoints": ((44000.0, -4000.0), (112000.0, 6000.0)),
        "length": 22500.0,
        "beam": 3230.0,
        "draft": 1420.0,
        "freeboard": 700.0,
        "mass": 87000.0 * 1000.0,
        "power": 9800000.0,
        "service_kn": 14.5,
    },
}

CONDITIONS = {
    "summer calm": {
        "time": 0.0,
        "wind_cms": 400.0,
        "wind_deg": 30.0,
        "current_cms": 25.0,
        "current_deg": 40.0,
        "wave_cm": 40.0,
        "wave_deg": 30.0,
    },
    "winter storm": {
        "time": 0.0,
        "wind_cms": 2200.0,
        "wind_deg": 210.0,
        "current_cms": 120.0,
        "current_deg": 130.0,
        "wave_cm": 400.0,
        "wave_deg": 200.0,
    },
}


def planned_cm(start, waypoints):
    total = 0.0
    previous = start
    for point in waypoints:
        total += math.hypot(point[0] - previous[0], point[1] - previous[1])
        previous = point
    return total


def distance_to_route(start, waypoints, point):
    points = (start,) + tuple(waypoints)
    best = 1.0e12
    for index in range(len(points) - 1):
        ax, ay = points[index]
        bx, by = points[index + 1]
        abx, aby = bx - ax, by - ay
        den = abx * abx + aby * aby
        along = 0.0
        if den > 1.0:
            along = max(0.0, min(1.0, ((point[0] - ax) * abx + (point[1] - ay) * aby) / den))
        closest = (ax + abx * along, ay + aby * along)
        best = min(best, math.hypot(point[0] - closest[0], point[1] - closest[1]))
    return best


def remaining_m(position, index, waypoints):
    remaining = math.hypot(waypoints[index][0] - position[0], waypoints[index][1] - position[1])
    for leg in range(index, len(waypoints) - 1):
        remaining += math.hypot(waypoints[leg + 1][0] - waypoints[leg][0], waypoints[leg + 1][1] - waypoints[leg][1])
    return remaining / 100.0


def autopilot(position, yaw, index, waypoints):
    if index < len(waypoints) - 1 and math.hypot(waypoints[index][0] - position[0], waypoints[index][1] - position[1]) < 8000.0:
        index += 1
    target = waypoints[index]
    dist_m = math.hypot(target[0] - position[0], target[1] - position[1]) / 100.0
    desired = 3.5 if dist_m < 220.0 else 6.0
    bearing = math.degrees(math.atan2(target[1] - position[1], target[0] - position[0]))
    rudder = max(-35.0, min(35.0, mmg.wrap_deg(bearing - yaw) * 1.15))
    return index, desired, rudder, remaining_m(position, index, waypoints)


def initial_state(spec):
    start = spec["start"]
    first = spec["waypoints"][0]
    bearing = math.degrees(math.atan2(first[1] - start[1], first[0] - start[0]))
    yaw = bearing + 8.0
    length_m = spec["length"] / 100.0
    beam_m = spec["beam"] / 100.0
    draft_m = spec["draft"] / 100.0
    freeboard_m = spec["freeboard"] / 100.0
    wetted = length_m * (beam_m + 2.0 * draft_m) * 0.85
    frontal = beam_m * freeboard_m
    lateral = length_m * freeboard_m
    service_cms = spec["service_kn"] * 0.514444 * 100.0
    ship = (
        yaw, 450.0, 0.0, 0.0, 0.0, 6.0, spec["mass"], spec["length"], spec["beam"], spec["draft"],
        spec["freeboard"], spec["power"], wetted, frontal, lateral, service_cms, start[0], start[1],
    )
    return ship


def sail(spec, condition):
    ship = initial_state(spec)
    env = dict(condition)
    index = 0
    elapsed = 0.0
    path = 0.0
    fuel = 0.0
    offset_sum = 0.0
    offset_max = 0.0
    samples = 0
    heave_peak = 0.0
    dt = 0.05
    arrived = False
    while elapsed < 600.0:
        yaw = ship[0]
        x, y = ship[16], ship[17]
        index, desired, rudder, remain = autopilot((x, y), yaw, index, spec["waypoints"])
        ship = ship[:4] + (rudder, desired) + ship[6:]
        ship, rate, heave, _, _ = mmg.integrate(ship, env, dt)
        yaw, surge, sway = ship[0], ship[1], ship[2]
        radians = math.radians(yaw)
        forward = (math.cos(radians), math.sin(radians))
        right = (-math.sin(radians), math.cos(radians))
        nx = x + (forward[0] * surge + right[0] * sway) * dt
        ny = y + (forward[1] * surge + right[1] * sway) * dt
        path += math.hypot(nx - x, ny - y)
        fuel += rate * dt / 3600.0
        offset = distance_to_route(spec["start"], spec["waypoints"], (nx, ny))
        offset_sum += offset
        offset_max = max(offset_max, offset)
        samples += 1
        heave_peak = max(heave_peak, abs(heave))
        ship = ship[:16] + (nx, ny)
        elapsed += dt
        if elapsed > 2.0 and remain < 80.0:
            arrived = True
            break
    mean_kn = (path / 100.0) / elapsed * 1.943844
    return {
        "sim": elapsed,
        "path_m": path / 100.0,
        "planned_m": planned_cm(spec["start"], spec["waypoints"]) / 100.0,
        "mean_offset_m": (offset_sum / samples) / 100.0 if samples else 0.0,
        "max_offset_m": offset_max / 100.0,
        "fuel_t": fuel,
        "mean_kn": mean_kn,
        "heave_peak_m": heave_peak / 100.0,
        "arrived": arrived,
    }


def main():
    lines = []
    for condition_name, condition in CONDITIONS.items():
        for name, spec in SHIPS.items():
            result = sail(spec, condition)
            status = "arrived" if result["arrived"] else "timed out"
            line = (
                f"VOYAGE {name} | {condition_name} | sim {result['sim']:.1f} s | "
                f"path {result['path_m']:.0f} m | planned {result['planned_m']:.0f} m | "
                f"mean offset {result['mean_offset_m']:.1f} m | max offset {result['max_offset_m']:.1f} m | "
                f"fuel {result['fuel_t']:.3f} t | mean {result['mean_kn']:.1f} kn | "
                f"heave peak {result['heave_peak_m']:.2f} m | {status}"
            )
            lines.append(line)
            print(line)
    out = os.path.join(os.path.dirname(__file__), "..", "data", "task3_voyage_comparison.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
