import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import baseline_helm
import mmg_env


CALM = {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}
BREEZE = {"wind_ms": 8.0, "wind_deg": 90.0, "current_ms": 0.6, "current_deg": 90.0, "wave_m": 0.4, "wave_deg": 90.0}


class BaselineHelmTest(unittest.TestCase):
    def test_straight_calm_destination_is_approached(self):
        env = mmg_env.MaritimeRoutingEnv(destination_m=(2500.0, 0.0), step_s=1.0, max_steps=40, sea=CALM)
        result = baseline_helm.run_from_reset(env, options={"heading_deg": 0.0})
        self.assertGreater(result["progress_m"], 100.0)
        self.assertLess(result["final_distance_m"], result["start_distance_m"])
        self.assertGreater(result["fuel_t"], 0.0)
        self.assertIn(result["termination"], ("arrived", "truncated", "running"))

    def test_offset_destination_and_initial_heading_still_close_distance(self):
        env = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 1500.0), step_s=1.0, max_steps=80, sea=CALM)
        result = baseline_helm.run_from_reset(env, options={"heading_deg": 50.0})
        self.assertGreater(result["progress_m"], 80.0)
        self.assertLess(result["final_distance_m"], result["start_distance_m"] - 80.0)

    def test_beam_disturbance_does_not_freeze_the_ship(self):
        env = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=30, sea=BREEZE)
        result = baseline_helm.run_from_reset(env, options={"heading_deg": 0.0})
        self.assertGreater(result["progress_m"], 50.0)
        self.assertGreater(result["route_m"], 50.0)

    def test_short_time_limit_truncates_before_arrival(self):
        env = mmg_env.MaritimeRoutingEnv(destination_m=(8000.0, 0.0), step_s=1.0, max_steps=3, sea=CALM)
        result = baseline_helm.run_from_reset(env, options={"heading_deg": 0.0})
        self.assertEqual(result["termination"], "truncated")
        self.assertGreater(result["progress_m"], 0.0)
        self.assertGreater(result["final_distance_m"], 150.0)

    def test_realistic_horizons_match_the_measured_speed(self):
        for name, destination, heading, steps, sea, expected in baseline_helm.realistic_scenarios():
            env = mmg_env.MaritimeRoutingEnv(destination_m=destination, step_s=1.0, max_steps=steps, sea=sea)
            result = baseline_helm.run_from_reset(env, options={"heading_deg": heading})
            self.assertEqual(result["termination"], expected, name)
            self.assertGreater(result["progress_m"], 0.0, name)
            self.assertGreater(result["route_m"], 0.0, name)
            self.assertGreater(result["fuel_t"], 0.0, name)
            if expected == "arrived":
                self.assertLessEqual(result["final_distance_m"], 150.0, name)
                self.assertLess(result["steps"], steps, name)
            else:
                self.assertGreater(result["final_distance_m"], 150.0, name)
                self.assertEqual(result["steps"], steps, name)


if __name__ == "__main__":
    unittest.main()
