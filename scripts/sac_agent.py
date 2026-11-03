"""Small Soft Actor-Critic agent in NumPy.

Fixed entropy temperature alpha = 0.2. Twin critics, target critics, and a
replay buffer. `train_smoke` refuses more than 256 steps unless the process
is explicitly allowed to call the validation gate. This is not a trained
navigation policy.
"""

import math
import os

import numpy as np

ALPHA = 0.2
GAMMA = 0.99
TAU = 0.01
MAX_UNATTENDED_STEPS = 256


def _relu(values):
    return np.maximum(values, 0.0)


class Adam:
    def __init__(self, shapes, lr):
        self.lr = lr
        self.m = [np.zeros(shape) for shape in shapes]
        self.v = [np.zeros(shape) for shape in shapes]
        self.t = 0

    def step(self, params, grads):
        self.t += 1
        for index, (param, grad) in enumerate(zip(params, grads)):
            self.m[index] = 0.9 * self.m[index] + 0.1 * grad
            self.v[index] = 0.999 * self.v[index] + 0.001 * (grad * grad)
            mhat = self.m[index] / (1.0 - 0.9 ** self.t)
            vhat = self.v[index] / (1.0 - 0.999 ** self.t)
            param -= self.lr * mhat / (np.sqrt(vhat) + 1.0e-8)


class MLP:
    def __init__(self, sizes, rng, lr=1.0e-3):
        self.sizes = list(sizes)
        self.weights = []
        self.biases = []
        for fan_in, fan_out in zip(sizes[:-1], sizes[1:]):
            scale = math.sqrt(2.0 / fan_in)
            self.weights.append(rng.normal(0.0, scale, (fan_in, fan_out)))
            self.biases.append(np.zeros(fan_out))
        self.optimizer = Adam([item.shape for pair in zip(self.weights, self.biases) for item in pair], lr)

    def params(self):
        values = []
        for weight, bias in zip(self.weights, self.biases):
            values.append(weight)
            values.append(bias)
        return values

    def forward(self, inputs):
        hidden = inputs
        cache = [inputs]
        for index, (weight, bias) in enumerate(zip(self.weights, self.biases)):
            linear = hidden @ weight + bias
            hidden = linear if index == len(self.weights) - 1 else _relu(linear)
            cache.append(hidden)
        return hidden, cache

    def backward(self, cache, grad):
        weight_grads = [None] * len(self.weights)
        bias_grads = [None] * len(self.biases)
        signal = grad
        for index in reversed(range(len(self.weights))):
            incoming = cache[index]
            if index < len(self.weights) - 1:
                signal = signal * (cache[index + 1] > 0.0)
            batch = max(incoming.shape[0], 1)
            weight_grads[index] = incoming.T @ signal / batch
            bias_grads[index] = signal.mean(axis=0)
            signal = signal @ self.weights[index].T
        grads = []
        for weight_grad, bias_grad in zip(weight_grads, bias_grads):
            grads.append(weight_grad)
            grads.append(bias_grad)
        self.optimizer.step(self.params(), grads)
        return signal


class ReplayBuffer:
    def __init__(self, capacity, obs_dim, act_dim):
        self.capacity = int(capacity)
        self.obs = np.zeros((self.capacity, obs_dim))
        self.actions = np.zeros((self.capacity, act_dim))
        self.rewards = np.zeros(self.capacity)
        self.next_obs = np.zeros((self.capacity, obs_dim))
        self.terminated = np.zeros(self.capacity)
        self.size = 0
        self.cursor = 0

    def add(self, obs, action, reward, next_obs, terminated):
        self.obs[self.cursor] = obs
        self.actions[self.cursor] = action
        self.rewards[self.cursor] = reward
        self.next_obs[self.cursor] = next_obs
        self.terminated[self.cursor] = float(terminated)
        self.cursor = (self.cursor + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch, rng):
        index = rng.integers(0, self.size, size=batch)
        return self.obs[index], self.actions[index], self.rewards[index], self.next_obs[index], self.terminated[index]


class SACAgent:
    def __init__(self, obs_dim, act_dim, seed=0, lr=1.0e-3, alpha=ALPHA):
        self.obs_dim = int(obs_dim)
        self.act_dim = int(act_dim)
        self.alpha = float(alpha)
        self.rng = np.random.default_rng(seed)
        self.actor = MLP([obs_dim, 32, 32, act_dim * 2], self.rng, lr)
        self.critic1 = MLP([obs_dim + act_dim, 32, 32, 1], self.rng, lr)
        self.critic2 = MLP([obs_dim + act_dim, 32, 32, 1], self.rng, lr)
        self.target1 = MLP([obs_dim + act_dim, 32, 32, 1], np.random.default_rng(seed + 1), lr)
        self.target2 = MLP([obs_dim + act_dim, 32, 32, 1], np.random.default_rng(seed + 2), lr)
        self._copy(self.critic1, self.target1)
        self._copy(self.critic2, self.target2)
        self.buffer = ReplayBuffer(20000, obs_dim, act_dim)

    @staticmethod
    def _copy(source, dest):
        for src, dst in zip(source.params(), dest.params()):
            dst[...] = src

    @staticmethod
    def _blend(source, dest, tau):
        for src, dst in zip(source.params(), dest.params()):
            dst[...] = (1.0 - tau) * dst + tau * src

    def _policy(self, obs, deterministic):
        raw, cache = self.actor.forward(obs)
        mean = raw[:, : self.act_dim]
        log_std = np.clip(raw[:, self.act_dim :], -5.0, 2.0)
        std = np.exp(log_std)
        if deterministic:
            latent = mean
        else:
            latent = mean + std * self.rng.normal(0.0, 1.0, size=mean.shape)
        action = np.tanh(latent)
        log_prob = -0.5 * (np.square((latent - mean) / (std + 1.0e-6)) + 2.0 * log_std + math.log(2.0 * math.pi))
        log_prob = log_prob.sum(axis=1) - np.log(1.0 - np.square(action) + 1.0e-6).sum(axis=1)
        return action, log_prob, cache, latent, mean, log_std

    def act(self, obs, deterministic=False):
        action, _, _, _, _, _ = self._policy(np.asarray(obs, dtype=np.float64)[None, :], deterministic)
        return np.clip(action[0], -1.0, 1.0)

    def observe(self, obs, action, reward, next_obs, terminated):
        self.buffer.add(obs, action, reward, next_obs, terminated)

    def update(self, batch=32):
        if self.buffer.size < 8:
            return {"updated": 0}
        obs, actions, rewards, next_obs, terminated = self.buffer.sample(min(batch, self.buffer.size), self.rng)
        next_action, next_log_prob, _, _, _, _ = self._policy(next_obs, deterministic=False)
        next_q1, _ = self.target1.forward(np.concatenate([next_obs, next_action], axis=1))
        next_q2, _ = self.target2.forward(np.concatenate([next_obs, next_action], axis=1))
        target = rewards + GAMMA * (1.0 - terminated) * (np.minimum(next_q1[:, 0], next_q2[:, 0]) - self.alpha * next_log_prob)
        target = target[:, None]
        self._critic_step(self.critic1, obs, actions, target)
        self._critic_step(self.critic2, obs, actions, target)
        new_action, log_prob, cache, latent, mean, log_std = self._policy(obs, deterministic=False)
        q1, _ = self.critic1.forward(np.concatenate([obs, new_action], axis=1))
        q2, _ = self.critic2.forward(np.concatenate([obs, new_action], axis=1))
        q_value = np.minimum(q1, q2)
        # d(alpha * log_pi - Q) / d(action). The tanh correction is local.
        std = np.exp(log_std)
        dlog_dlatent = -((latent - mean) / (np.square(std) + 1.0e-6))
        dlog_dlatent = dlog_dlatent + (2.0 * new_action / (1.0 - np.square(new_action) + 1.0e-6)) * (1.0 - np.square(new_action))
        actor_signal = (self.alpha * dlog_dlatent) * (1.0 - np.square(new_action))
        # Q increases the action toward the critic's finite difference of one step.
        q_taken = q_value[:, 0:1]
        probe = 1.0e-2
        plus = np.concatenate([obs, np.clip(new_action + probe, -1.0, 1.0)], axis=1)
        minus = np.concatenate([obs, np.clip(new_action - probe, -1.0, 1.0)], axis=1)
        q_plus, _ = self.critic1.forward(plus)
        q_minus, _ = self.critic1.forward(minus)
        d_q = (q_plus - q_minus) / (2.0 * probe)
        actor_signal = actor_signal - d_q
        raw_grad = np.concatenate([
            actor_signal,
            np.zeros_like(actor_signal),
        ], axis=1)
        # log_std is not the direct action path in this smoke update.
        self.actor.backward(cache, raw_grad / max(np.mean(np.abs(raw_grad)), 1.0e-3))
        self._blend(self.critic1, self.target1, TAU)
        self._blend(self.critic2, self.target2, TAU)
        return {"updated": 1, "q": float(np.mean(q_taken)), "log_prob": float(np.mean(log_prob))}

    @staticmethod
    def _critic_step(critic, obs, actions, target):
        joined = np.concatenate([obs, actions], axis=1)
        prediction, cache = critic.forward(joined)
        grad = 2.0 * (prediction - target)
        critic.backward(cache, grad)

    def save(self, path):
        payload = {"alpha": np.array([self.alpha]), "obs_dim": np.array([self.obs_dim]), "act_dim": np.array([self.act_dim])}
        for label, net in (("actor", self.actor), ("critic1", self.critic1), ("critic2", self.critic2), ("target1", self.target1), ("target2", self.target2)):
            for index, param in enumerate(net.params()):
                payload["%s_%d" % (label, index)] = param.copy()
        np.savez(path, **payload)

    def load(self, path):
        data = np.load(path)
        if int(data["obs_dim"][0]) != self.obs_dim or int(data["act_dim"][0]) != self.act_dim:
            raise ValueError("checkpoint shape does not match this agent")
        self.alpha = float(data["alpha"][0])
        for label, net in (("actor", self.actor), ("critic1", self.critic1), ("critic2", self.critic2), ("target1", self.target1), ("target2", self.target2)):
            for index, param in enumerate(net.params()):
                param[...] = data["%s_%d" % (label, index)]


def train_smoke(env, max_steps=32, seed=0, checkpoint_path=None):
    if max_steps > MAX_UNATTENDED_STEPS:
        if os.environ.get("MARITIME_ALLOW_TRAIN") != "1":
            raise SystemExit("refusing a long training run (%d steps)" % max_steps)
        from pretrain_validate import enforce_training_gate
        enforce_training_gate()
    agent = SACAgent(env.observation_space.shape[0], env.action_space.shape[0], seed=seed)
    obs, _ = env.reset(seed=seed)
    updates = 0
    for _ in range(max_steps):
        action = agent.act(obs, deterministic=False)
        next_obs, reward, terminated, truncated, _ = env.step(action)
        agent.observe(obs, action, reward, next_obs, terminated)
        result = agent.update(batch=16)
        updates += result.get("updated", 0)
        obs = next_obs
        if terminated or truncated:
            obs, _ = env.reset(seed=seed + updates + 1)
    if checkpoint_path:
        agent.save(checkpoint_path)
    return agent, updates


def evaluate_policy(env, agent, episodes=2, max_steps=20, seed=1):
    rewards = []
    progress = []
    effort = []
    arrived = 0
    failed = 0
    truncated = 0
    for episode in range(episodes):
        obs, info = env.reset(seed=seed + episode)
        total = 0.0
        moved = 0.0
        effort_sum = 0.0
        steps = 0
        done = False
        while steps < max_steps and not done:
            action = agent.act(obs, deterministic=True)
            obs, reward, terminated, is_truncated, info = env.step(action)
            total += reward
            moved += info["progress_m"]
            effort_sum += info["effort"]
            steps += 1
            if info["failure"]:
                failed += 1
            if terminated or is_truncated:
                arrived += int(info["arrived"])
                truncated += int(is_truncated and not terminated)
                done = True
        rewards.append(total)
        progress.append(moved)
        effort.append(effort_sum / max(steps, 1))
    return {
        "episodes": episodes,
        "mean_reward": float(np.mean(rewards)),
        "mean_progress_m": float(np.mean(progress)),
        "mean_effort": float(np.mean(effort)),
        "arrived": arrived,
        "failures": failed,
        "truncated": truncated,
    }
