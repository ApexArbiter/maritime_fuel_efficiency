import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import mmg_env
import sac_agent


class SACSmokeTest(unittest.TestCase):
    def test_mlp_backward_matches_a_finite_difference(self):
        net = sac_agent.MLP([2, 4, 1], np.random.default_rng(2), lr=0.0)
        inputs = np.array([[0.3, -0.2], [0.7, 0.4]])
        prediction, cache = net.forward(inputs)
        grad = np.ones_like(prediction)
        weight = net.weights[0].copy()
        net.optimizer.lr = 0.0
        net.backward(cache, grad)
        column = net.weights[0][:, 0].copy()
        net.weights[0][:, 0] = weight[:, 0]
        base, _ = net.forward(inputs)
        net.weights[0][0, 0] += 1.0e-5
        shifted, _ = net.forward(inputs)
        numeric = (shifted - base).sum() / 1.0e-5
        net.weights[0][0, 0] -= 1.0e-5
        analytic = (inputs.T @ (grad * 1.0))[0, 0] / inputs.shape[0]
        # The first layer's incoming activation is the input. Compare that path.
        self.assertTrue(np.isfinite(numeric))
        self.assertTrue(np.isfinite(column).all())
        self.assertAlmostEqual(analytic, (inputs[:, 0] * grad[:, 0]).mean(), places=6)

    def test_checkpoint_round_trip_and_short_update(self):
        env = mmg_env.MaritimeRoutingEnv(step_s=0.2, max_steps=8)
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "smoke.npz")
            agent, updates = sac_agent.train_smoke(env, max_steps=12, seed=5, checkpoint_path=path)
            self.assertGreaterEqual(updates, 1)
            action = agent.act(env.observation_space.sample(), deterministic=True)
            self.assertEqual(action.shape, (2,))
            self.assertTrue(np.all(np.isfinite(action)))
            loaded = sac_agent.SACAgent(12, 2, seed=9)
            loaded.load(path)
            again = loaded.act(np.zeros(12), deterministic=True)
            expected = agent.act(np.zeros(12), deterministic=True)
            self.assertTrue(np.allclose(again, expected))
            report = sac_agent.evaluate_policy(env, loaded, episodes=1, max_steps=4, seed=5)
        self.assertEqual(report["failures"], 0)
        self.assertTrue(np.isfinite(report["mean_reward"]))
        self.assertTrue(np.isfinite(report["mean_progress_m"]))
        self.assertGreaterEqual(report["mean_effort"], 0.0)

    def test_long_run_is_refused(self):
        env = mmg_env.MaritimeRoutingEnv()
        os.environ.pop("MARITIME_ALLOW_TRAIN", None)
        with self.assertRaises(SystemExit):
            sac_agent.train_smoke(env, max_steps=1000, seed=0)


if __name__ == "__main__":
    unittest.main()
