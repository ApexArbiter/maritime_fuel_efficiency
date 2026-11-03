import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import mmg_env
import mmg_physics as mmg


class RouteContractTest(unittest.TestCase):
    def test_shapes_bounds_and_reset_repeat(self):
        env = mmg_env.MaritimeRoutingEnv()
        first, _ = env.reset(seed=4, options={"heading_deg": 12.0})
        again, _ = env.reset(seed=4, options={"heading_deg": 12.0})
        self.assertEqual(first.shape, (mmg_env.OBSERVATION_DIM,))
        self.assertEqual(len(mmg_env.OBSERVATION_FIELDS), 12)
        self.assertTrue(np.array_equal(first, again))
        self.assertTrue(env.observation_space.contains(first))
        self.assertTrue(np.all(np.isfinite(first)))
        action = np.array([0.2, -0.4])
        self.assertTrue(env.action_space.contains(action))
        _, _, _, _, info = env.step(action)
        self.assertEqual(info["rudder_deg"], 0.2 * 35.0)
        self.assertTrue(np.isfinite(info["ordered_speed_ms"]))
        self.assertEqual(info["inner_dt_s"], 0.02)
        observation = env._observe()
        self.assertAlmostEqual(observation[4], info["heading_error_rad"] / math.pi, places=6)
        self.assertAlmostEqual(observation[6], info["rudder_deg"] / 35.0, places=6)
        self.assertAlmostEqual(observation[11], info["distance_m"] / 8000.0, places=6)
        self.assertAlmostEqual(observation[2], info["surge_ms"] / (env.ship[15] / 100.0), places=6)

    def test_position_advances_once_per_substep(self):
        env = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=5)
        env.reset(options={"heading_deg": 0.0})
        calls = []
        real = mmg_env.advance_position

        def wrapped(ship, dt):
            calls.append(dt)
            return real(ship, dt)

        mmg_env.advance_position = wrapped
        try:
            _, reward, terminated, truncated, info = env.step(np.array([0.0, 1.0]))
        finally:
            mmg_env.advance_position = real
        self.assertEqual(len(calls), int(round(1.0 / 0.02)))
        self.assertTrue(all(abs(dt - 0.02) < 1.0e-12 for dt in calls))
        self.assertFalse(terminated)
        self.assertFalse(truncated)
        expected = info["progress_reward"] + info["deviation_reward"] + info["effort_reward"] + info["fuel_reward"]
        self.assertAlmostEqual(reward, expected, places=6)
        self.assertGreater(info["x_m"], 3.0)
        self.assertLess(info["x_m"], 8.0)

    def test_mmg_does_not_move_the_position_and_the_env_does(self):
        env = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=5)
        env.reset(seed=None)
        held = env.ship
        clock = dict(env.clock)
        returned, _, _, _, _ = mmg.integrate(held, clock, 1.0)
        self.assertEqual(returned[16], held[16])
        self.assertEqual(returned[17], held[17])
        _, _, _, _, info = env.step(np.array([0.0, 1.0]))
        self.assertGreater(info["progress_m"], 3.0)
        self.assertGreater(info["x_m"], 3.0)
        self.assertEqual(info["collision"], False)
        self.assertIsNone(info["separation_m"])

    def test_overlap_terminates_and_a_near_miss_does_not(self):
        other = {"x_m": 100.0, "y_m": 0.0, "heading_deg": 0.0, "length_m": 300.0, "beam_m": 40.0}
        blocked = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=0.2, max_steps=5, traffic=[other])
        blocked.reset(options={"heading_deg": 0.0})
        _, reward, terminated, truncated, info = blocked.step(np.array([0.0, 0.0]))
        self.assertTrue(info["collision"])
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertLess(reward, 0.0)
        near = {"x_m": 270.0, "y_m": 0.0, "heading_deg": 0.0, "length_m": 200.0, "beam_m": 30.0}
        passing = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=0.2, max_steps=5, traffic=[near])
        passing.reset(options={"heading_deg": 0.0})
        _, _, terminated, truncated, info = passing.step(np.array([0.0, 0.0]))
        self.assertFalse(info["collision"])
        self.assertTrue(info["near_miss"])
        self.assertFalse(terminated)
        self.assertFalse(truncated)


if __name__ == "__main__":
    unittest.main()
