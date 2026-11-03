"""Reward terms. The coefficient 0.05 per kilogram is an initial value."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import mmg_env


FLAT = {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}


class RewardTermTest(unittest.TestCase):
    def test_each_term_matches_a_hand_calculation(self):
        parts = mmg_env.routing_reward(20.0, 400.0, 1.0, 0.0, 2.0, arrived=False, failed=False, fuel_reward_per_kg=0.05)
        self.assertAlmostEqual(parts["progress_reward"], 1.0, places=9)
        self.assertAlmostEqual(parts["deviation_reward"], -1.0, places=9)
        self.assertAlmostEqual(parts["effort_reward"], -0.05, places=9)
        self.assertAlmostEqual(parts["fuel_reward"], -0.1, places=9)
        self.assertAlmostEqual(parts["reward"], 1.0 - 1.0 - 0.05 - 0.1, places=9)
        reverse = mmg_env.routing_reward(-10.0, 0.0, 0.0, 0.0, 0.0, fuel_reward_per_kg=0.05)
        self.assertAlmostEqual(reverse["progress_reward"], -0.5, places=9)
        zero = mmg_env.routing_reward(0.0, 0.0, 0.0, 0.0, 0.0, fuel_reward_per_kg=0.05)
        self.assertEqual(zero["reward"], 0.0)
        arrived = mmg_env.routing_reward(0.0, 0.0, 0.0, 0.0, 0.0, arrived=True, fuel_reward_per_kg=0.05)
        self.assertEqual(arrived["arrival_reward"], 10.0)
        failed = mmg_env.routing_reward(0.0, 0.0, 0.0, 0.0, 0.0, failed=True, fuel_reward_per_kg=0.05)
        self.assertEqual(failed["failure_reward"], -10.0)
        baseline = mmg_env.routing_reward(20.0, 400.0, 1.0, 0.0, 2.0, fuel_reward_per_kg=0.0)
        self.assertEqual(baseline["fuel_reward"], 0.0)
        self.assertAlmostEqual(baseline["reward"], 1.0 - 1.0 - 0.05, places=9)
        self.assertEqual(mmg_env.step_fuel_tonnes(float("nan"), 0.02), 0.0)

    def test_environment_reward_matches_the_function_and_arrival_is_once(self):
        env = mmg_env.make_routing_env(destination_m=(2000.0, 0.0), step_s=0.2, max_steps=4, sea=FLAT, fuel_reward_per_kg=0.05)
        env.reset(options={"heading_deg": 0.0})
        _, reward, terminated, truncated, info = env.step(np.array([0.0, 1.0]))
        self.assertAlmostEqual(info["effort"], 1.0, places=6)
        expected = mmg_env.routing_reward(
            info["progress_m"], info["cross_track_m"], 0.0, 1.0, info["fuel_kg"],
            arrived=False, failed=False, fuel_reward_per_kg=0.05,
        )
        self.assertAlmostEqual(reward, expected["reward"], places=9)
        self.assertAlmostEqual(info["fuel_reward"], -info["fuel_kg"] * 0.05, places=9)
        self.assertGreater(info["fuel_kg"], 0.0)
        self.assertLess(abs(info["fuel_reward"]), abs(info["progress_reward"]))
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertEqual(info["reward_name"], mmg_env.REWARD_NAME)

        close = mmg_env.make_routing_env(destination_m=(20.0, 0.0), success_radius_m=50.0, step_s=0.2, max_steps=4, sea=FLAT, fuel_reward_per_kg=0.0)
        close.reset(options={"heading_deg": 0.0})
        _, _, terminated, truncated, first = close.step(np.array([0.0, 0.0]))
        self.assertTrue(first["arrived"])
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertEqual(first["arrival_reward"], 10.0)
        _, _, _, _, second = close.step(np.array([0.0, -1.0]))
        self.assertTrue(second["arrived"])
        self.assertEqual(second["arrival_reward"], 0.0)

        far = mmg_env.make_routing_env(destination_m=(6000.0, 0.0), max_steps=1, step_s=0.2, sea=FLAT, fuel_reward_per_kg=0.0)
        far.reset(options={"heading_deg": 0.0})
        _, reward, terminated, truncated, info = far.step(np.array([0.0, 0.0]))
        self.assertTrue(truncated)
        self.assertFalse(terminated)
        self.assertEqual(info["arrival_reward"], 0.0)
        self.assertEqual(info["failure_reward"], 0.0)
        self.assertAlmostEqual(reward, info["progress_reward"] + info["deviation_reward"] + info["effort_reward"], places=9)

    def test_same_route_with_more_fuel_scores_lower_and_is_not_double_counted(self):
        baseline = mmg_env.routing_reward(40.0, 100.0, 0.2, 0.5, 0.0, fuel_reward_per_kg=0.0)
        current = mmg_env.routing_reward(40.0, 100.0, 0.2, 0.5, 3.0, fuel_reward_per_kg=0.05)
        heavier = mmg_env.routing_reward(40.0, 100.0, 0.2, 0.5, 8.0, fuel_reward_per_kg=0.05)
        self.assertEqual(baseline["fuel_reward"], 0.0)
        self.assertAlmostEqual(current["progress_reward"], baseline["progress_reward"], places=9)
        self.assertAlmostEqual(current["deviation_reward"], baseline["deviation_reward"], places=9)
        self.assertAlmostEqual(current["effort_reward"], baseline["effort_reward"], places=9)
        self.assertAlmostEqual(current["fuel_reward"], -0.15, places=9)
        self.assertLess(current["reward"], baseline["reward"])
        self.assertLess(heavier["reward"], current["reward"])
        arrived = mmg_env.routing_reward(40.0, 100.0, 0.2, 0.5, 8.0, arrived=True, fuel_reward_per_kg=0.05)
        failed = mmg_env.routing_reward(40.0, 0.0, 0.0, 1.0, 1.0, failed=True, fuel_reward_per_kg=0.05)
        self.assertGreater(arrived["arrival_reward"], abs(arrived["fuel_reward"]))
        self.assertLess(failed["failure_reward"], arrived["fuel_reward"])
        short_kg = mmg_env.step_fuel_tonnes(1.0, 0.02) * 1000.0
        long_kg = mmg_env.step_fuel_tonnes(1.0, 1.0) * 1000.0
        self.assertAlmostEqual(long_kg, short_kg * 50.0, places=9)
        again = mmg_env.routing_reward(40.0, 100.0, 0.2, 0.5, 3.0, fuel_reward_per_kg=0.05)
        self.assertEqual(again["reward"], current["reward"])
        print(
            "REWARD_COMPARE baseline=%.6f fuel_term=%.6f penalised=%.6f heavier=%.6f arrival=%.6f failure=%.6f"
            % (baseline["reward"], current["fuel_reward"], current["reward"], heavier["reward"], arrived["reward"], failed["reward"])
        )


if __name__ == "__main__":
    unittest.main()
