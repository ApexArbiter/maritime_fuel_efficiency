import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import mmg_env
import mmg_physics as mmg


class MaritimeEnvTest(unittest.TestCase):
    def test_spaces_and_reset_are_deterministic(self):
        first = mmg_env.MaritimeRoutingEnv()
        second = mmg_env.MaritimeRoutingEnv()
        obs_a, info_a = first.reset(seed=7)
        obs_b, _ = second.reset(seed=7)
        self.assertEqual(obs_a.shape, (12,))
        self.assertTrue(first.observation_space.contains(obs_a))
        self.assertTrue(np.array_equal(obs_a, obs_b))
        self.assertGreater(info_a["distance_m"], 1000.0)
        action = first.action_space.sample()
        self.assertEqual(action.shape, (2,))
        self.assertTrue(first.action_space.contains(action))

    def test_step_uses_mmg_and_reports_reward_parts(self):
        env = mmg_env.MaritimeRoutingEnv(step_s=0.2, max_steps=10)
        env.reset(seed=3)
        ship, command = mmg_env.apply_action(env.ship, np.array([0.25, 0.5]))
        clock = dict(env.clock)
        expected, fuel, _, _, _ = mmg.integrate(ship, clock, 0.2)
        obs, reward, terminated, truncated, info = env.step(np.array([0.25, 0.5]))
        self.assertTrue(env.observation_space.contains(obs))
        self.assertTrue(math.isfinite(reward))
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        self.assertAlmostEqual(env.ship[0], expected[0], places=6)
        self.assertAlmostEqual(env.ship[1], expected[1], places=4)
        self.assertAlmostEqual(info["fuel_tph"], fuel, places=6)
        self.assertIn("progress_reward", info)
        self.assertAlmostEqual(info["wave_m"], 0.4)
        self.assertEqual(info["inner_dt_s"], 0.02)
        self.assertAlmostEqual(command[0], 0.25)

    def test_termination_truncation_and_invalid_actions(self):
        close = mmg_env.MaritimeRoutingEnv(destination_m=(20.0, 0.0), success_radius_m=50.0, max_steps=5)
        close.reset(seed=1)
        _, _, terminated, truncated, info = close.step(np.array([0.0, 0.0]))
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertTrue(info["arrived"])
        far = mmg_env.MaritimeRoutingEnv(destination_m=(6000.0, 0.0), max_steps=2, step_s=0.2)
        far.reset(seed=1)
        far.step(np.array([0.0, 0.0]))
        _, _, terminated, truncated, info = far.step(np.array([0.0, 0.0]))
        self.assertFalse(terminated)
        self.assertTrue(truncated)
        self.assertFalse(info["failure"])
        env = mmg_env.MaritimeRoutingEnv()
        env.reset(seed=1)
        with self.assertRaises(ValueError):
            env.step(np.array([float("nan"), 0.0]))
        with self.assertRaises(ValueError):
            env.step(np.array([0.0]))

    def test_default_episode_has_no_traffic(self):
        env = mmg_env.MaritimeRoutingEnv()
        env.reset(seed=1)
        _, _, _, _, info = env.step(np.array([0.0, 0.0]))
        self.assertFalse(info["collision"])
        self.assertFalse(info["near_miss"])
        self.assertIsNone(info["separation_m"])
        self.assertEqual(env.traffic, [])


if __name__ == "__main__":
    unittest.main()
