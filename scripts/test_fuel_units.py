"""Fuel-unit regression. The adopted consumption is 175 g/kWh.

`fuel_rate_kg_s` returns kilograms per second. The live simulation, the UDP
reply, and the voyage accumulator all use tonnes per hour derived from that
rate (`kg/s * 3.6`). There is no Gym environment and no reward function in
this repository. The reported single-step reward of -2327 is compared with
the fuel term below and is not equal to it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import mmg_physics as mmg

INSTALLED_POWER_KW = (45700.0, 13500.0, 9800.0)


def shaft_power_w(ship):
    """Shaft power for the calm, still-air state `step_once` uses.

    Still air is a headwind equal to the ship's own speed, so the wind force
    is not zero.
    """
    surge_ms = ship[1] / 100.0
    wetted = ship[12]
    frontal = ship[13]
    resist = 0.5 * mmg.RHO_WATER * 0.0018 * wetted * surge_ms * abs(surge_ms)
    wind_surge_ms = -surge_ms
    wind_surge_n = 0.5 * mmg.RHO_AIR * 0.8 * frontal * wind_surge_ms * abs(wind_surge_ms)
    useful = max(0.0, resist - wind_surge_n)
    return min(ship[11], useful * max(surge_ms, 0.4) / 0.55)


class FuelUnitTest(unittest.TestCase):
    def test_zero_power_is_zero_fuel(self):
        self.assertEqual(mmg.fuel_rate_kg_s(0.0), 0.0)
        ship = (
            0.0, 797.0, 0.0, 0.0, 0.0, 8.0, 1.45e8, 30000.0, 4280.0, 1450.0, 800.0,
            0.0, 18309.0, 342.4, 2400.0, 1157.0, 0.0, 0.0,
        )
        _, fuel_tph, _, _, _ = mmg.step_once(ship, {"time": 0.0, "wind_cms": 0.0, "wind_deg": 0.0, "current_cms": 0.0, "current_deg": 0.0, "wave_cm": 0.0, "wave_deg": 0.0}, 0.02)
        self.assertEqual(fuel_tph, 0.0)

    def test_one_thousand_kilowatts(self):
        rate = mmg.fuel_rate_kg_s(1000.0)
        hour_kg = rate * 3600.0
        print("FUEL_KG_S power_kw=1000 rate_kg_s=%.10f hour_kg=%.6f" % (rate, hour_kg))
        self.assertAlmostEqual(rate, 0.0486111111, places=7)
        self.assertAlmostEqual(hour_kg, 175.0, places=6)
        self.assertAlmostEqual(rate * 1000.0, 1000.0 * 175.0 / 3600.0, places=6)

    def test_step_fuel_uses_the_kg_s_rate(self):
        surge_ms = 15.5 * mmg.KNOT_MS
        length_m, beam_m, draft_m, freeboard_m = 300.0, 42.8, 14.5, 8.0
        wetted = length_m * (beam_m + 2.0 * draft_m) * 0.85
        ship = (
            0.0, surge_ms * 100.0, 0.0, 0.0, 0.0, surge_ms, 1.45e8, 30000.0, 4280.0, 1450.0, 800.0,
            45700000.0, wetted, beam_m * freeboard_m, length_m * freeboard_m, 22.5 * mmg.KNOT_MS * 100.0, 0.0, 0.0,
        )
        env = {"time": 0.0, "wind_cms": 0.0, "wind_deg": 0.0, "current_cms": 0.0, "current_deg": 0.0, "wave_cm": 0.0, "wave_deg": 0.0}
        _, fuel_tph, _, _, _ = mmg.step_once(ship, env, 0.02)
        expected_tph = mmg.fuel_rate_kg_s(shaft_power_w(ship) / 1000.0) * 3.6
        self.assertAlmostEqual(fuel_tph, expected_tph, places=9)
        self.assertLess(fuel_tph, expected_tph * 1.001 + 1.0e-9)

    def test_voyage_counter_accumulates_corrected_tonnes(self):
        tonnes_per_hour = mmg.fuel_rate_kg_s(1000.0) * 3.6
        fuel_t = 0.0
        dt = 1.0
        for _ in range(3600):
            fuel_t += tonnes_per_hour * dt / 3600.0
        self.assertAlmostEqual(fuel_t * 1000.0, 175.0, places=6)

    def test_udp_reply_carries_the_same_tonnes_per_hour(self):
        surge_ms = 15.5 * mmg.KNOT_MS
        length_m, beam_m, draft_m, freeboard_m = 300.0, 42.8, 14.5, 8.0
        wetted = length_m * (beam_m + 2.0 * draft_m) * 0.85
        header = mmg.HEADER.pack(mmg.REQ, 1, 1, 0.02, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        body = mmg.SHIP.pack(
            7, 0.0, 0.0, 0.0, surge_ms * 100.0, 0.0, 0.0, 0.0, surge_ms, 1.45e8, 30000.0, 4280.0,
            1450.0, 800.0, 45700000.0, wetted, beam_m * freeboard_m, length_m * freeboard_m, 22.5 * mmg.KNOT_MS * 100.0,
        )
        reply = mmg.handle(header + body)
        self.assertIsNotNone(reply)
        values = mmg.REPLY.unpack_from(reply, 12)
        fuel_tph = values[8]
        ship = (
            0.0, surge_ms * 100.0, 0.0, 0.0, 0.0, surge_ms, 1.45e8, 30000.0, 4280.0, 1450.0, 800.0,
            45700000.0, wetted, beam_m * freeboard_m, length_m * freeboard_m, 22.5 * mmg.KNOT_MS * 100.0, 0.0, 0.0,
        )
        _, direct, _, _, _ = mmg.step_once(ship, {"time": 0.0, "wind_cms": 0.0, "wind_deg": 0.0, "current_cms": 0.0, "current_deg": 0.0, "wave_cm": 0.0, "wave_deg": 0.0}, 0.02)
        self.assertAlmostEqual(fuel_tph, direct, places=6)

    def test_reported_reward_is_not_the_fuel_term(self):
        reported = 2327.0
        print("REWARD_INVESTIGATION reported=-2327 gym=none reward_function=none")
        for power_kw in INSTALLED_POWER_KW:
            corrected = mmg.fuel_rate_kg_s(power_kw)
            buggy = power_kw * 175.0 / 3600.0
            self.assertGreater(abs(corrected - reported), 1.0)
            self.assertGreater(abs(buggy - reported), 1.0)
            print(
                "REWARD_INVESTIGATION power_kw=%.0f corrected_kg_s=%.6f buggy_kg_s=%.3f"
                % (power_kw, corrected, buggy)
            )


if __name__ == "__main__":
    unittest.main()
