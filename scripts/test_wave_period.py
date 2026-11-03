import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import mmg_physics as mmg
import wave_period as period


class WavePeriodTest(unittest.TestCase):
    def test_physical_period_matches_the_fixed_90_m_wave(self):
        seconds = period.physical_wave_period_s()
        self.assertAlmostEqual(seconds, 7.596, places=2)
        self.assertAlmostEqual(mmg.wave_surface(0.0, 0.0, 100.0, 0.0, seconds), 0.0, places=3)
        self.assertAlmostEqual(mmg.wave_surface(0.0, 0.0, 100.0, 0.0, seconds / 4.0), -100.0, places=3)

    def test_visual_period_clamps_and_does_not_change_wave_height(self):
        state = {"wave_cm": 130.0, "wave_deg": 30.0}
        low = period.with_visual_period(state, 1.0)
        high = period.with_visual_period(state, 40.0)
        nominal = period.with_visual_period(state, 8.0)
        self.assertEqual(low["visual_period_s"], 4.0)
        self.assertEqual(high["visual_period_s"], 18.0)
        self.assertAlmostEqual(nominal["visual_omega_scale"], 1.0)
        self.assertAlmostEqual(low["visual_omega_scale"], 2.0)
        self.assertAlmostEqual(high["visual_omega_scale"], 8.0 / 18.0)
        self.assertEqual(state["wave_cm"], 130.0)
        self.assertEqual(low["wave_cm"], 130.0)
        with self.assertRaises(ValueError):
            period.clamp_visual_period(float("nan"))

    def test_visual_period_does_not_change_the_physical_surface(self):
        before = mmg.wave_surface(1000.0, -500.0, 280.0, 200.0, 3.0)
        period.with_visual_period({"wave_cm": 280.0}, 4.0)
        after = mmg.wave_surface(1000.0, -500.0, 280.0, 200.0, 3.0)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
