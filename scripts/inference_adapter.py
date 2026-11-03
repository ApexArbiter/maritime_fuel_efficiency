"""Boundary for a policy that another person is still designing.

`act(observation)` must return two finite numbers. This module does not
choose a tensor framework, a dtype, or a checkpoint format. Those stay
pending. It also does not send helm to the live fleet. The Unreal autopilot
keeps the UDP socket.
"""

import math
from threading import Thread

FALLBACK_ACTION = (0.0, -1.0)
DEFAULT_TIMEOUT_S = 0.25
CONTROL_PERIOD_S = 1.0
PENDING = (
    "checkpoint path",
    "framework and dtype",
    "native tensor layout",
    "control period if it is not 1 second",
    "whether inference replaces the UDP autopilot",
)


class AdapterRejected(ValueError):
    """The observation or the model output is outside the contract."""


def as_observation(observation):
    try:
        count = len(observation)
        values = [float(observation[index]) for index in range(12)]
    except (TypeError, ValueError, IndexError, KeyError):
        raise AdapterRejected("observation must be 12 finite numbers in [-1, 1]")
    if count != 12 or not all(math.isfinite(value) and -1.0 <= value <= 1.0 for value in values):
        raise AdapterRejected("observation must be 12 finite numbers in [-1, 1]")
    return tuple(values)


def as_action(raw):
    try:
        count = len(raw)
        values = [float(raw[0]), float(raw[1])]
    except (TypeError, ValueError, IndexError, KeyError):
        raise AdapterRejected("action must be two finite numbers")
    if count != 2 or not all(math.isfinite(value) for value in values):
        raise AdapterRejected("action must be two finite numbers")
    return (max(-1.0, min(1.0, values[0])), max(-1.0, min(1.0, values[1])))


class DummyAdapter:
    """Returns one fixed action. This is not the incoming model."""

    def __init__(self, action=(0.0, 0.0)):
        self.action = as_action(action)

    def act(self, observation):
        as_observation(observation)
        return self.action


def guarded_act(adapter, observation, fallback=FALLBACK_ACTION, timeout_s=DEFAULT_TIMEOUT_S):
    """Return `(action, status)`. Discard a late result and any non-finite output.

    Status is `ok`, `invalid_observation`, `invalid_action`, or `timeout`.
    The fallback is zero rudder and an ordered stop. The caller must not
    forward either result onto the live UDP autopilot.
    """
    safe = as_action(fallback)
    try:
        as_observation(observation)
    except AdapterRejected:
        return safe, "invalid_observation"
    box = {}

    def run():
        try:
            box["action"] = adapter.act(observation)
        except Exception as exc:
            box["error"] = exc

    worker = Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        return safe, "timeout"
    if "error" in box or "action" not in box:
        return safe, "invalid_action"
    try:
        return as_action(box["action"]), "ok"
    except AdapterRejected:
        return safe, "invalid_action"


def attach_to_fleet(adapter, address):
    """Refuse a live connection. The fleet autopilot is unchanged."""
    raise RuntimeError("UDP autopilot retained; %s is not attached to %s" % (type(adapter).__name__, address))
