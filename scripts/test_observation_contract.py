"""Observation and action contract. Values are checked against the divisors."""

import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import inference_adapter
import mmg_env


FLAT = {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}

EXPECTED_FIELDS = (
    "destination_offset_x",
    "destination_offset_y",
    "surge",
    "sway",
    "heading_error",
    "yaw_rate",
    "rudder",
    "wind",
    "current",
    "wave_height",
    "cross_track",
    "distance",
)


class ObservationContractTest(unittest.TestCase):
    def test_field_order_normalization_and_clipping(self):
        self.assertEqual(mmg_env.OBSERVATION_FIELDS, EXPECTED_FIELDS)
        self.assertEqual(mmg_env.OBSERVATION_DIM, 12)
        self.assertEqual(mmg_env.ACTION_DIM, 2)
        env = mmg_env.make_routing_env(destination_m=(8000.0, 0.0), sea=dict(FLAT))
        env.reset(options={"heading_deg": 0.0})
        service_cms = env.ship[15]
        values = list(env.ship)
        values[1] = service_cms
        values[2] = 400.0
        values[3] = 0.12
        values[4] = 35.0
        env.ship = tuple(values)
        env.sea = {"wind_ms": 35.0, "wind_deg": 0.0, "current_ms": 3.0, "current_deg": 0.0, "wave_m": 6.0, "wave_deg": 0.0}
        observation = env._observe()
        self.assertEqual(observation.shape, (12,))
        self.assertTrue(np.all(np.isfinite(observation)))
        self.assertAlmostEqual(observation[0], 1.0, places=6)
        self.assertAlmostEqual(observation[1], 0.0, places=6)
        self.assertAlmostEqual(observation[2], 1.0, places=6)
        self.assertAlmostEqual(observation[3], 1.0, places=6)
        self.assertAlmostEqual(observation[4], 0.0, places=6)
        self.assertAlmostEqual(observation[5], 1.0, places=6)
        self.assertAlmostEqual(observation[6], 1.0, places=6)
        self.assertAlmostEqual(observation[7], 1.0, places=6)
        self.assertAlmostEqual(observation[8], 1.0, places=6)
        self.assertAlmostEqual(observation[9], 1.0, places=6)
        self.assertAlmostEqual(observation[11], 1.0, places=6)

        env.destination_m = (-8000.0, 0.0)
        behind = env._observe()
        self.assertAlmostEqual(behind[4], -1.0, places=6)

        env.destination_m = (0.0, 8000.0)
        values = list(env.ship)
        values[16] = 100000.0
        values[17] = 0.0
        env.ship = tuple(values)
        off_track = env._observe()
        self.assertAlmostEqual(off_track[10], 1.0, places=6)

        env.destination_m = (20000.0, 0.0)
        values = list(env.ship)
        values[1] = service_cms * 3.0
        values[16] = 0.0
        values[17] = 0.0
        env.ship = tuple(values)
        clipped = env._observe()
        self.assertAlmostEqual(clipped[0], 1.0, places=6)
        self.assertAlmostEqual(clipped[2], 1.0, places=6)
        self.assertTrue(np.all(clipped <= 1.0) and np.all(clipped >= -1.0))

    def test_actions_and_adapter_agree_with_the_contract(self):
        env = mmg_env.make_routing_env(destination_m=(2000.0, 0.0), step_s=0.2, max_steps=4, sea=FLAT)
        env.reset(options={"heading_deg": 0.0})
        service = env.ship[15] / 100.0
        stopped, _ = mmg_env.apply_action(env.ship, np.array([-1.0, -1.0]))
        middle, _ = mmg_env.apply_action(env.ship, np.array([0.0, 0.0]))
        full, _ = mmg_env.apply_action(env.ship, np.array([1.0, 1.0]))
        self.assertAlmostEqual(stopped[4], -35.0, places=6)
        self.assertAlmostEqual(stopped[5], 0.0, places=6)
        self.assertAlmostEqual(middle[4], 0.0, places=6)
        self.assertAlmostEqual(middle[5], 0.5 * service, places=6)
        self.assertAlmostEqual(full[4], 35.0, places=6)
        self.assertAlmostEqual(full[5], service, places=6)
        clipped, _ = mmg_env.apply_action(env.ship, np.array([2.0, -3.0]))
        self.assertAlmostEqual(clipped[4], 35.0, places=6)
        self.assertAlmostEqual(clipped[5], 0.0, places=6)
        with self.assertRaises(ValueError):
            env.step(np.array([float("nan"), 0.0]))
        with self.assertRaises(ValueError):
            env.step(np.array([float("inf"), 0.0]))
        with self.assertRaises(ValueError):
            env.step(np.array([0.0]))

        observation, _ = env.reset(options={"heading_deg": 0.0})
        action, status = inference_adapter.guarded_act(inference_adapter.DummyAdapter((0.0, 0.0)), observation)
        self.assertEqual(status, "ok")
        _, _, _, _, info = env.step(action)
        self.assertAlmostEqual(info["rudder_deg"], 0.0, places=6)
        self.assertAlmostEqual(info["ordered_speed_ms"], 0.5 * service, places=5)
        fallback, fallback_status = inference_adapter.guarded_act(inference_adapter.DummyAdapter((0.0, 0.0)), [float("nan")] * 12)
        self.assertEqual(fallback_status, "invalid_observation")
        self.assertEqual(fallback, (0.0, -1.0))


if __name__ == "__main__":
    unittest.main()
