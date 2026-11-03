"""Direct entry point for the routing environment.

No external training package is imported. A count of zero registered trainers
is the expected gate result.
"""

import importlib.util
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import mmg_env
import pretrain_validate


def _flat():
    return {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}


class DiscoveryTest(unittest.TestCase):
    def test_documented_entry_point_resets_steps_and_closes(self):
        self.assertEqual(mmg_env.ENV_ID, "MaritimeRouting-v0")
        self.assertEqual(mmg_env.ENTRY_POINT, "mmg_env:make_routing_env")
        self.assertEqual(pretrain_validate.training_entry_points(), [])
        env = mmg_env.make_routing_env(destination_m=(800.0, 0.0), step_s=0.2, max_steps=6, sea=_flat())
        self.assertIsInstance(env, mmg_env.MaritimeRoutingEnv)
        observation, info = env.reset(seed=2, options={"heading_deg": 0.0})
        self.assertEqual(observation.shape, (mmg_env.OBSERVATION_DIM,))
        self.assertTrue(env.observation_space.contains(observation))
        self.assertTrue(np.all(np.isfinite(observation)))
        self.assertGreater(info["distance_m"], 0.0)
        action = np.array([0.0, 0.0])
        self.assertTrue(env.action_space.contains(action))
        for _ in range(3):
            observation, reward, terminated, truncated, info = env.step(action)
            self.assertTrue(env.observation_space.contains(observation))
            self.assertTrue(math.isfinite(reward))
            self.assertTrue(np.all(np.isfinite(observation)))
            self.assertIn(info["termination"], ("running", "arrived", "truncated", "failure", "collision"))
            self.assertIsInstance(terminated, bool)
            self.assertIsInstance(truncated, bool)
        env.close()
        with self.assertRaises(RuntimeError):
            env.step(action)
        with self.assertRaises(RuntimeError):
            env.reset()

    def test_external_training_packages_are_absent(self):
        self.assertIsNone(importlib.util.find_spec("gym" + "nasium"))
        self.assertIsNone(importlib.util.find_spec("torch"))


if __name__ == "__main__":
    unittest.main()
