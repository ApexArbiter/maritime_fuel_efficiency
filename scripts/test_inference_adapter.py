import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import inference_adapter
import mmg_env


class InferenceAdapterTest(unittest.TestCase):
    def test_dummy_action_is_finite_and_reaches_the_helm(self):
        env = mmg_env.MaritimeRoutingEnv(destination_m=(400.0, 0.0), step_s=1.0, max_steps=2)
        observation, _ = env.reset(options={"heading_deg": 0.0})
        adapter = inference_adapter.DummyAdapter((0.25, -1.0))
        action, status = inference_adapter.guarded_act(adapter, observation)
        self.assertEqual(status, "ok")
        self.assertEqual(action, (0.25, -1.0))
        _, _, _, _, info = env.step(action)
        self.assertAlmostEqual(info["rudder_deg"], 0.25 * 35.0, places=6)
        self.assertEqual(info["ordered_speed_ms"], 0.0)

    def test_invalid_output_uses_the_stop_fallback(self):
        class NanAdapter:
            def act(self, observation):
                return (float("nan"), 1.0)

        observation = [0.0] * 12
        action, status = inference_adapter.guarded_act(NanAdapter(), observation, timeout_s=1.0)
        self.assertEqual(status, "invalid_action")
        self.assertEqual(action, inference_adapter.FALLBACK_ACTION)
        env = mmg_env.MaritimeRoutingEnv()
        env.reset(options={"heading_deg": 0.0})
        _, _, _, _, info = env.step(action)
        self.assertEqual(info["rudder_deg"], 0.0)
        self.assertEqual(info["ordered_speed_ms"], 0.0)

    def test_timeout_discards_the_late_action(self):
        class SlowAdapter:
            def act(self, observation):
                time.sleep(0.3)
                return (1.0, 1.0)

        action, status = inference_adapter.guarded_act(SlowAdapter(), [0.0] * 12, timeout_s=0.05)
        self.assertEqual(status, "timeout")
        self.assertEqual(action, inference_adapter.FALLBACK_ACTION)

    def test_bad_observation_does_not_call_the_adapter(self):
        called = []

        class Recording:
            def act(self, observation):
                called.append(True)
                return (0.0, 0.0)

        action, status = inference_adapter.guarded_act(Recording(), [0.0] * 11)
        self.assertEqual(status, "invalid_observation")
        self.assertEqual(action, inference_adapter.FALLBACK_ACTION)
        self.assertEqual(called, [])

    def test_live_fleet_attachment_is_refused(self):
        with self.assertRaises(RuntimeError):
            inference_adapter.attach_to_fleet(inference_adapter.DummyAdapter(), "127.0.0.1:9001")


if __name__ == "__main__":
    unittest.main()
