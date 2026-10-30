"""Turning-circle regression for the container ship at 15.5 kn and 35 degrees.

Diameter in this test is the steady turning diameter, `2*U/r`, once the yaw
rate has settled. Advance is the distance along the original course from the
rudder-execute point until the heading has changed 90 degrees. Tactical
diameter, the cross-track distance at a 180 degree heading change, is printed
and is not used as the 960 m check. A first-order Nomoto model that matches
both the steady diameter and the advance produces a larger tactical diameter.
Forcing the tactical diameter and the advance onto the same two targets needs
a yaw time constant of several minutes, which is not a ship response.

The hull is the 300 m container ship. The tanker and the bulker cannot hold
15.5 kn because their service speeds are 15.0 kn and 14.5 kn.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import mmg_physics as mmg

DT = 0.05
RUDDER_DEG = 35.0


def container_state(rudder_deg, surge_cms):
    length_cm = 30000.0
    beam_cm = 4280.0
    draft_cm = 1450.0
    freeboard_cm = 800.0
    length_m = length_cm / 100.0
    beam_m = beam_cm / 100.0
    draft_m = draft_cm / 100.0
    freeboard_m = freeboard_cm / 100.0
    speed_ms = mmg.REFERENCE_SPEED_KN * mmg.KNOT_MS
    return (
        0.0,
        surge_cms,
        0.0,
        0.0,
        rudder_deg,
        speed_ms,
        145000.0 * 1000.0,
        length_cm,
        beam_cm,
        draft_cm,
        freeboard_cm,
        45700000.0,
        length_m * (beam_m + 2.0 * draft_m) * 0.85,
        beam_m * freeboard_m,
        length_m * freeboard_m,
        22.5 * mmg.KNOT_MS * 100.0,
        0.0,
        0.0,
    )


def calm():
    return {
        "time": 0.0,
        "wind_cms": 0.0,
        "wind_deg": 0.0,
        "current_cms": 0.0,
        "current_deg": 0.0,
        "wave_cm": 0.0,
        "wave_deg": 0.0,
    }


def unwrap_delta(previous, current):
    delta = current - previous
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta


def step_track(ship, env, rudder_deg, dt):
    speed_ms = mmg.REFERENCE_SPEED_KN * mmg.KNOT_MS
    ship = ship[:4] + (rudder_deg, speed_ms) + ship[6:]
    previous_yaw = ship[0]
    x_cm, y_cm = ship[16], ship[17]
    ship, fuel, heave, pitch, roll = mmg.integrate(ship, env, dt)
    yaw, surge, sway = ship[0], ship[1], ship[2]
    radians = math.radians(yaw)
    forward = (math.cos(radians), math.sin(radians))
    right = (-math.sin(radians), math.cos(radians))
    x_cm += (forward[0] * surge + right[0] * sway) * dt
    y_cm += (forward[1] * surge + right[1] * sway) * dt
    ship = ship[:16] + (x_cm, y_cm)
    return ship, unwrap_delta(previous_yaw, yaw), fuel


def measure_turn(rudder_deg):
    env = calm()
    speed_cms = mmg.REFERENCE_SPEED_KN * mmg.KNOT_MS * 100.0
    ship = container_state(0.0, speed_cms)
    for _ in range(int(20.0 / DT)):
        ship, _, _ = step_track(ship, env, 0.0, DT)
    ship = ship[:16] + (0.0, 0.0)
    heading = 0.0
    advance_m = None
    tactical_m = None
    steady = []
    for _ in range(int(2500.0 / DT)):
        ship, delta_heading, _ = step_track(ship, env, rudder_deg, DT)
        heading += delta_heading
        x_m = ship[16] / 100.0
        y_m = ship[17] / 100.0
        if advance_m is None and heading >= 90.0:
            advance_m = x_m
        if tactical_m is None and heading >= 180.0:
            tactical_m = abs(y_m)
        if heading >= 400.0:
            speed = math.hypot(ship[1], ship[2]) / 100.0
            steady.append(2.0 * speed / abs(ship[3]))
        if heading >= 500.0:
            break
    return {
        "advance_m": advance_m,
        "tactical_diameter_m": tactical_m,
        "steady_diameter_m": sum(steady) / len(steady),
        "approach_kn": (ship[1] / 100.0) / mmg.KNOT_MS,
    }


class TurningCircleTest(unittest.TestCase):
    def test_reference_turn(self):
        result = measure_turn(RUDDER_DEG)
        steady = result["steady_diameter_m"]
        advance = result["advance_m"]
        tactical = result["tactical_diameter_m"]
        print(
            "TURNING_CIRCLE steady_diameter_m=%.3f advance_m=%.3f tactical_diameter_m=%.3f approach_kn=%.3f"
            % (steady, advance, tactical, result["approach_kn"])
        )
        self.assertGreaterEqual(steady, 864.0)
        self.assertLessEqual(steady, 1056.0)
        self.assertGreaterEqual(advance, 892.8)
        self.assertLessEqual(advance, 1091.2)
        self.assertIsNotNone(tactical)

    def test_straight_line_holds_heading(self):
        env = calm()
        speed_cms = mmg.REFERENCE_SPEED_KN * mmg.KNOT_MS * 100.0
        ship = container_state(0.0, speed_cms)
        heading = 0.0
        for _ in range(int(120.0 / DT)):
            ship, delta_heading, _ = step_track(ship, env, 0.0, DT)
            heading += delta_heading
        self.assertLess(abs(heading), 0.5)
        self.assertLess(abs(ship[17]) / 100.0, 5.0)
        self.assertLess(abs(ship[3]), 1.0e-4)

    def test_smaller_rudder_makes_a_wider_circle(self):
        hard = measure_turn(35.0)
        easier = measure_turn(20.0)
        self.assertGreater(easier["steady_diameter_m"], hard["steady_diameter_m"] * 1.4)
        self.assertGreater(easier["steady_diameter_m"], 1400.0)


if __name__ == "__main__":
    unittest.main()
