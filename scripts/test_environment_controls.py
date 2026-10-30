"""Environment controls that the MMG step actually consumes.

Weather in this project is four named presets. Each preset is a fixed wind,
current, and wave triple. There is no separate clear, cloudy, or rain force.
Wave length is fixed at 90 m inside wave_surface. Direction 0 is +X, toward +Y.
Current is subtracted from ground velocity for the water-relative drag, and its
sway component also pulls the sway velocity. It is not added to surge.
"""

import math
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import mmg_physics as mmg

# The same numbers AFleetEnvironment::ApplyPreset writes onto the UDP header.
PRESETS = {
    "summer calm": (4.0, 30.0, 0.25, 40.0, 0.4, 30.0),
    "spring tide": (8.0, 110.0, 1.40, 120.0, 1.3, 110.0),
    "autumn gale": (18.0, 200.0, 0.70, 190.0, 2.8, 200.0),
    "winter storm": (22.0, 210.0, 1.20, 130.0, 4.0, 200.0),
}

CONTAINER = (
    0.0, 400.0, 0.0, 0.0, 0.0, 6.0, 1.45e8, 30000.0, 4280.0, 1450.0, 800.0,
    4.57e7, 18000.0, 340.0, 2400.0, 1157.0, 0.0, 0.0,
)


def env_from_ms(wind_ms, wind_deg, current_ms, current_deg, wave_m, wave_deg, sim_time=0.0):
    return {
        "time": sim_time,
        "wind_cms": wind_ms * 100.0,
        "wind_deg": wind_deg,
        "current_cms": current_ms * 100.0,
        "current_deg": current_deg,
        "wave_cm": wave_m * 100.0,
        "wave_deg": wave_deg,
    }


def run(ship, env, seconds, dt=0.05):
    clock = dict(env)
    steps = int(seconds / dt)
    last = None
    for _ in range(steps):
        ship, fuel, heave, pitch, roll = mmg.integrate(ship, clock, dt)
        last = (ship, fuel, heave, pitch, roll, clock["time"])
    return last


def packet(seq, dt, sim_time, wind_cms, wind_deg, current_cms, current_deg, wave_cm, wave_deg):
    header = mmg.HEADER.pack(mmg.REQ, seq, 1, dt, sim_time, wind_cms, wind_deg, current_cms, current_deg, wave_cm, wave_deg)
    body = mmg.SHIP.pack(
        1, 0.0, 0.0, 0.0, 400.0, 0.0, 0.0, 0.0, 6.0, 1.45e8, 30000.0, 4280.0,
        1450.0, 800.0, 4.57e7, 18000.0, 340.0, 2400.0, 1157.0,
    )
    return header + body


class EnvironmentControlTest(unittest.TestCase):
    def test_supported_presets_are_accepted_and_echoed(self):
        for name, values in PRESETS.items():
            wind_ms, wind_deg, current_ms, current_deg, wave_m, wave_deg = values
            reply = mmg.handle(packet(3, 0.05, 1.0, wind_ms * 100.0, wind_deg, current_ms * 100.0, current_deg, wave_m * 100.0, wave_deg))
            self.assertTrue(reply.startswith(mmg.REP))
            self.assertIn(b"ACK1", reply)
            ack = mmg.ACK.unpack_from(reply, reply.index(b"ACK1"))
            self.assertAlmostEqual(ack[1], wind_ms * 100.0, places=3)
            self.assertAlmostEqual(ack[3], current_ms * 100.0, places=3)
            self.assertAlmostEqual(ack[5], wave_m * 100.0, places=3)
            self.assertNotIn(name, ("clear", "cloudy", "rain"))

    def test_unsupported_non_finite_packet_is_rejected(self):
        reply = mmg.handle(packet(4, 0.05, 0.0, float("nan"), 0.0, 0.0, 0.0, 0.0, 0.0))
        self.assertTrue(reply.endswith(b"REJ1"))
        self.assertNotIn(b"ACK1", reply)
        count = struct.unpack_from("<I", reply, 8)[0]
        self.assertEqual(count, 0)

    def test_out_of_range_values_are_clamped_not_invented(self):
        clamped = mmg.clamp_environment(9000.0, 400.0, -5.0, -20.0, 2000.0, 10.0)
        self.assertEqual(clamped["wind_cms"], 3500.0)
        self.assertEqual(clamped["current_cms"], 0.0)
        self.assertEqual(clamped["wave_cm"], 600.0)
        self.assertAlmostEqual(clamped["wind_deg"], 40.0)
        self.assertAlmostEqual(clamped["current_deg"], 340.0)

    def test_zero_current_stays_near_the_heading_and_a_beam_current_creates_sway(self):
        still = env_from_ms(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        beam = env_from_ms(0.0, 0.0, 1.5, 90.0, 0.0, 0.0)
        zero = run(CONTAINER, still, 30.0)
        pushed = run(CONTAINER, beam, 30.0)
        self.assertLess(abs(zero[0][2]), 30.0)
        self.assertGreater(abs(pushed[0][2]), abs(zero[0][2]) + 20.0)

    def test_head_waves_add_resistance_and_heave(self):
        calm = env_from_ms(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        head = env_from_ms(0.0, 0.0, 0.0, 0.0, 3.0, 180.0)
        calm_end = run(CONTAINER, calm, 20.0)
        wave_end = run(CONTAINER, head, 20.0)
        self.assertGreater(calm_end[0][1], wave_end[0][1])
        self.assertGreater(abs(wave_end[2]), abs(calm_end[2]))

    def test_wave_period_is_not_an_input(self):
        self.assertNotIn("wave_period", mmg.HEADER.format)
        one = mmg.wave_surface(0.0, 0.0, 100.0, 0.0, 0.0)
        # 90 m wavelength, so a point 90 m along +X is the same phase.
        shifted = mmg.wave_surface(9000.0, 0.0, 100.0, 0.0, 0.0)
        self.assertAlmostEqual(one, shifted, places=4)

    def test_pause_dt_does_not_advance_simulation_time(self):
        clock = env_from_ms(4.0, 30.0, 0.25, 40.0, 0.4, 30.0, sim_time=12.0)
        mmg.integrate(CONTAINER, clock, 0.0)
        self.assertEqual(clock["time"], 12.0)

    def test_long_frame_keeps_the_0_02_second_substep(self):
        coarse = env_from_ms(4.0, 30.0, 0.0, 0.0, 0.0, 0.0)
        fine = env_from_ms(4.0, 30.0, 0.0, 0.0, 0.0, 0.0)
        coarse_end = run(CONTAINER, coarse, 2.0, dt=0.2)
        fine_end = run(CONTAINER, fine, 2.0, dt=0.02)
        self.assertAlmostEqual(coarse_end[0][1], fine_end[0][1], delta=5.0)
        self.assertAlmostEqual(coarse_end[5], 2.0, places=5)

    def test_winter_storm_changes_sway_relative_to_summer_calm(self):
        summer = env_from_ms(*PRESETS["summer calm"])
        winter = env_from_ms(*PRESETS["winter storm"])
        summer_end = run(CONTAINER, summer, 25.0)
        winter_end = run(CONTAINER, winter, 25.0)
        self.assertGreater(abs(winter_end[0][2] - summer_end[0][2]), 5.0)

    def test_existing_ship_reply_still_unpacks_ahead_of_the_ack(self):
        reply = mmg.handle(packet(9, 0.02, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
        values = mmg.REPLY.unpack_from(reply, 12)
        self.assertEqual(len(values), 10)
        self.assertTrue(math.isfinite(values[8]))


if __name__ == "__main__":
    unittest.main()
