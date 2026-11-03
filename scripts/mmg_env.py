"""Gym-compatible routing environment. Motion comes from `mmg_physics.integrate`.

Observations are clipped to [-1, 1]. Units before clipping:

0. destination offset x, metres / 8000
1. destination offset y, metres / 8000
2. surge, m/s / service speed
3. sway, m/s / 4
4. heading error, radians / pi
5. yaw rate, rad/s / 0.12
6. rudder, degrees / 35
7. wind, m/s / 35
8. current, m/s / 3
9. wave height, m / 6
10. cross-track error, metres / 1000
11. distance to destination, metres / 8000

Actions are clipped to [-1, 1]:

0. rudder fraction, mapped to [-35, 35] degrees
1. ordered-speed fraction. -1 is stop, 0 is half service speed, +1 is service speed.

`mmg_physics.integrate` returns the same x and y it was given. The fleet applies
the new surge and sway in `AFleetShip::ApplyMotion`, and the turning-circle
test does the same after each integrate. This environment applies that
kinematic update after every 0.02 s MMG step. It does not change the MMG
equations.

The default episode has one hull and no chart. `chart=None` means navigable
water was not checked; it is not proof that the water is safe. When a chart
is supplied, land or insufficient depth stops the ship on the last pose that
was still clear. Squat is not modeled. The required depth is static draft
plus a configurable under-keel clearance, default 2.0 m.

Optional `traffic` rectangles can be supplied. Overlap terminates the
episode. A gap below `near_miss_m` is flagged. Traffic that includes a
finite velocity can replace the requested helm before the physics step.
The replacement is the geometric subset in `encounter.py`, not full COLREG.
Live Unreal ships are not wired in yet. Hotel load is not in the ship tuple
and stays unavailable. The reward includes an initial fuel penalty. Set
`fuel_reward_per_kg=0` to recover the earlier reward, which had no fuel term.
Construct episodes with `make_routing_env`. That function is the training
entry point. No external training framework is registered.

Termination is arrival, overlap, or a non-finite state. Truncation is the
step limit. The inner MMG step stays 0.02 s.
"""

import math

import numpy as np

import mmg_physics as mmg
import hull_separation as separation
import navigable_water as water
import encounter as encounter_check

CONTRACT_VERSION = 3
ENV_ID = "MaritimeRouting-v0"
ENTRY_POINT = "mmg_env:make_routing_env"
OBSERVATION_DIM = 12
ACTION_DIM = 2
RUDDER_LIMIT_DEG = 35.0
SUCCESS_RADIUS_M = 150.0
INNER_DT_S = 0.02
NEAR_MISS_M = 50.0
OVERLAP_PENALTY = 10.0
ARRIVAL_REWARD = 10.0
# Initial penalty, reward units per kilogram. Not a fuel price and not
# calibrated on a voyage. A typical early step burns a fraction of a kilogram,
# so this stays smaller than progress (metres / 20) and much smaller than
# arrival (+10) or the overlap penalty (-10).
DEFAULT_FUEL_REWARD_PER_KG = 0.05
REWARD_NAME = "routing_reward"
# No hotel-load measurement is available. The 0.55 term in
# `mmg_physics.step_once` stays there; it is not an engine map.
HOTEL_LOAD_KW = None
UNDER_KEEL_CLEARANCE_M = water.UNDER_KEEL_CLEARANCE_M
SEA_FIELDS = ("wind_ms", "wind_deg", "current_ms", "current_deg", "wave_m", "wave_deg")

OBSERVATION_FIELDS = (
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


class BoxSpace:
    """Continuous box with the same role as a Gymnasium Box."""

    def __init__(self, low, high, rng):
        self.low = np.asarray(low, dtype=np.float64)
        self.high = np.asarray(high, dtype=np.float64)
        self.shape = self.low.shape
        self.dtype = np.float64
        self._rng = rng

    def contains(self, value):
        array = np.asarray(value, dtype=np.float64)
        return array.shape == self.shape and np.all(array >= self.low) and np.all(array <= self.high) and np.all(np.isfinite(array))

    def sample(self):
        return self._rng.uniform(self.low, self.high)


def reference_ship(surge_cms=450.0):
    return (
        0.0, surge_cms, 0.0, 0.0, 0.0, 6.0, 1.45e8, 30000.0, 4280.0, 1450.0, 800.0,
        4.57e7, 18000.0, 340.0, 2400.0, 1157.0, 0.0, 0.0,
    )


def apply_action(ship, action):
    """Return a ship tuple whose helm and ordered speed follow the action."""
    command = np.asarray(action, dtype=np.float64)
    if command.shape != (ACTION_DIM,) or not np.all(np.isfinite(command)):
        raise ValueError("action must be two finite numbers")
    command = np.clip(command, -1.0, 1.0)
    rudder = float(command[0] * RUDDER_LIMIT_DEG)
    service_ms = ship[15] / 100.0
    desired_ms = float((command[1] * 0.5 + 0.5) * service_ms)
    values = list(ship)
    values[4] = rudder
    values[5] = desired_ms
    return tuple(values), command


def advance_position(ship, dt):
    """Match the fleet and the turning-circle tracker. MMG itself does not do this."""
    yaw = math.radians(ship[0])
    forward = (math.cos(yaw), math.sin(yaw))
    right = (-math.sin(yaw), math.cos(yaw))
    values = list(ship)
    values[16] = ship[16] + (forward[0] * ship[1] + right[0] * ship[2]) * dt
    values[17] = ship[17] + (forward[1] * ship[1] + right[1] * ship[2]) * dt
    return tuple(values)


def step_fuel_tonnes(fuel_tph, dt_s):
    """Tonnes from one already-computed rate. A bad rate contributes nothing."""
    if isinstance(fuel_tph, bool) or isinstance(dt_s, bool):
        return 0.0
    if not isinstance(fuel_tph, (int, float)) or not isinstance(dt_s, (int, float)):
        return 0.0
    if not math.isfinite(fuel_tph) or not math.isfinite(dt_s) or fuel_tph < 0.0 or dt_s < 0.0:
        return 0.0
    return fuel_tph * dt_s / 3600.0


def routing_reward(progress_m, cross_track_m, rudder_fraction, speed_fraction, fuel_kg, arrived=False, failed=False, fuel_reward_per_kg=DEFAULT_FUEL_REWARD_PER_KG):
    """Return the reward actually used by `MaritimeRoutingEnv.step`.

    `fuel_kg` is the fuel added during this control step, counted once.
    `arrived=True` adds +10 once per call. The environment passes that flag
    only on the first arriving step. `failed=True` subtracts 10 for a
    non-finite state, an overlap, or a chart rejection.
    """
    numbers = (progress_m, cross_track_m, rudder_fraction, speed_fraction, fuel_reward_per_kg)
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) for value in numbers):
        raise ValueError("reward inputs must be finite")
    if fuel_reward_per_kg < 0.0:
        raise ValueError("fuel reward coefficient must be non-negative")
    if isinstance(fuel_kg, bool) or not isinstance(fuel_kg, (int, float)) or not math.isfinite(fuel_kg) or fuel_kg < 0.0:
        fuel_kg = 0.0
    progress_reward = float(progress_m) / 20.0
    deviation_reward = -abs(float(cross_track_m)) / 400.0
    effort_reward = -0.05 * float(rudder_fraction ** 2 + speed_fraction ** 2)
    fuel_reward = -float(fuel_kg) * float(fuel_reward_per_kg)
    reward = progress_reward + deviation_reward + effort_reward + fuel_reward
    arrival_reward = ARRIVAL_REWARD if arrived else 0.0
    failure_reward = -OVERLAP_PENALTY if failed else 0.0
    reward += arrival_reward + failure_reward
    return {
        "reward": reward,
        "progress_reward": progress_reward,
        "deviation_reward": deviation_reward,
        "effort_reward": effort_reward,
        "fuel_reward": fuel_reward,
        "fuel_kg": float(fuel_kg),
        "arrival_reward": arrival_reward,
        "failure_reward": failure_reward,
        "reward_name": REWARD_NAME,
    }


def _cross_track_m(x_m, y_m, destination):
    length = math.hypot(destination[0], destination[1])
    if length < 1.0:
        return 0.0
    return (x_m * destination[1] - y_m * destination[0]) / length


class MaritimeRoutingEnv:
    """One container ship, one destination, summer calm unless replaced."""

    metadata = {"render_modes": []}

    def __init__(self, destination_m=(6000.0, 800.0), step_s=1.0, max_steps=300, success_radius_m=SUCCESS_RADIUS_M, sea=None, traffic=None, near_miss_m=NEAR_MISS_M, chart=None, under_keel_clearance_m=UNDER_KEEL_CLEARANCE_M, min_separation_m=100.0, encounter_horizon_s=180.0, fuel_reward_per_kg=DEFAULT_FUEL_REWARD_PER_KG):
        self.destination_m = (float(destination_m[0]), float(destination_m[1]))
        self.step_s = float(step_s)
        self.max_steps = int(max_steps)
        self.success_radius_m = float(success_radius_m)
        self.sea = sea or {"wind_ms": 4.0, "wind_deg": 30.0, "current_ms": 0.25, "current_deg": 40.0, "wave_m": 0.4, "wave_deg": 30.0}
        self.traffic = list(traffic or [])
        self.near_miss_m = float(near_miss_m)
        self.chart = chart
        if not math.isfinite(under_keel_clearance_m) or under_keel_clearance_m < 0.0:
            raise ValueError("under-keel clearance must be finite and non-negative")
        if not math.isfinite(min_separation_m) or min_separation_m < 0.0:
            raise ValueError("minimum separation must be finite and non-negative")
        if not math.isfinite(encounter_horizon_s) or encounter_horizon_s <= 0.0:
            raise ValueError("encounter horizon must be finite and positive")
        if isinstance(fuel_reward_per_kg, bool) or not isinstance(fuel_reward_per_kg, (int, float)) or not math.isfinite(fuel_reward_per_kg) or fuel_reward_per_kg < 0.0:
            raise ValueError("fuel reward coefficient must be finite and non-negative")
        self.under_keel_clearance_m = float(under_keel_clearance_m)
        self.min_separation_m = float(min_separation_m)
        self.encounter_horizon_s = float(encounter_horizon_s)
        self.fuel_reward_per_kg = float(fuel_reward_per_kg)
        self._closed = False
        self._arrival_paid = False
        self._rng = np.random.default_rng(0)
        self.observation_space = BoxSpace(np.full(OBSERVATION_DIM, -1.0), np.full(OBSERVATION_DIM, 1.0), self._rng)
        self.action_space = BoxSpace(np.full(ACTION_DIM, -1.0), np.full(ACTION_DIM, 1.0), self._rng)
        self.ship = reference_ship()
        self.clock = {}
        self.steps = 0
        self._distance_m = 0.0

    def seed(self, seed):
        self.reset(seed=seed)

    def close(self):
        """Release the episode. There is no socket or renderer to shut down."""
        self._closed = True

    def reset(self, seed=None, options=None):
        if self._closed:
            raise RuntimeError("environment is closed")
        if seed is not None:
            self._rng = np.random.default_rng(int(seed))
            self.observation_space._rng = self._rng
            self.action_space._rng = self._rng
        if options and "heading_deg" in options:
            heading = float(options["heading_deg"])
        elif seed is None:
            heading = 0.0
        else:
            heading = float(self._rng.uniform(-15.0, 15.0))
        self.ship = reference_ship()
        values = list(self.ship)
        values[0] = heading
        self.ship = tuple(values)
        self.clock = {
            "time": 0.0,
            "wind_cms": self.sea["wind_ms"] * 100.0,
            "wind_deg": self.sea["wind_deg"],
            "current_cms": self.sea["current_ms"] * 100.0,
            "current_deg": self.sea["current_deg"],
            "wave_cm": self.sea["wave_m"] * 100.0,
            "wave_deg": self.sea["wave_deg"],
        }
        self.steps = 0
        self._arrival_paid = False
        observation = self._observe()
        self._distance_m = self._raw_distance_m()
        return observation, {"distance_m": self._distance_m, "seed": seed}

    def set_sea(self, sea):
        """Replace wind, current, and wave inputs used by the physics clock.

        Visual atmosphere fields are not accepted here. Magnitudes must be
        finite and non-negative. Directions follow `mmg_physics.direction`:
        degrees from +X toward +Y.
        """
        if not isinstance(sea, dict):
            raise ValueError("sea must be a dict")
        cleaned = {}
        for key in SEA_FIELDS:
            value = sea.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("sea field %s is missing or non-finite" % key)
            cleaned[key] = float(value)
        if cleaned["wind_ms"] < 0.0 or cleaned["current_ms"] < 0.0 or cleaned["wave_m"] < 0.0:
            raise ValueError("wind, current, and wave magnitudes cannot be negative")
        self.sea = cleaned
        if self.clock:
            self.clock["wind_cms"] = cleaned["wind_ms"] * 100.0
            self.clock["wind_deg"] = cleaned["wind_deg"]
            self.clock["current_cms"] = cleaned["current_ms"] * 100.0
            self.clock["current_deg"] = cleaned["current_deg"]
            self.clock["wave_cm"] = cleaned["wave_m"] * 100.0
            self.clock["wave_deg"] = cleaned["wave_deg"]
        return dict(self.sea)

    def step(self, action):
        if self._closed:
            raise RuntimeError("environment is closed")
        requested = np.asarray(action, dtype=np.float64)
        if requested.shape != (ACTION_DIM,) or not np.all(np.isfinite(requested)):
            raise ValueError("action must be two finite numbers")
        decision = self._traffic_decision()
        steered = decision["override"] if decision["override"] is not None else requested
        chart_now = self._chart_at(self._own_hull())
        before = self._raw_distance_m()
        start_x, start_y = self.ship[16], self.ship[17]
        blocked = water.blocking(chart_now)
        fuel = heave = pitch = roll = 0.0
        fuel_t = 0.0
        if blocked:
            command = np.clip(requested, -1.0, 1.0)
        else:
            self.ship, command = apply_action(self.ship, steered)
            remaining = self.step_s
            while remaining > 1.0e-9:
                step_dt = min(INNER_DT_S, remaining)
                stamp = self.clock["time"]
                pose = self.ship
                saved_motion = (heave, pitch, roll, fuel)
                ship, fuel, heave, pitch, roll = mmg.integrate(self.ship, self.clock, step_dt)
                # integrate leaves x,y untouched. Advance them the way the fleet does.
                candidate = advance_position(ship, step_dt)
                verdict = self._chart_at(self._hull_from_ship(candidate), previous=self._hull_from_ship(pose))
                if water.blocking(verdict):
                    self.ship = pose
                    self.clock["time"] = stamp
                    heave, pitch, roll, fuel = saved_motion
                    chart_now = verdict
                    blocked = True
                    break
                self.ship = candidate
                fuel_t += step_fuel_tonnes(fuel, step_dt)
                remaining -= step_dt
            if not blocked:
                chart_now = self._chart_at(self._own_hull())
        self.steps += 1
        failed = not all(math.isfinite(value) for value in self.ship)
        distance = self._raw_distance_m()
        gap = self._traffic_gap_m()
        collided = gap is not None and gap <= 0.0
        near_miss = gap is not None and 0.0 < gap < self.near_miss_m
        arrived = distance <= self.success_radius_m and not collided and not blocked
        truncated = self.steps >= self.max_steps and not arrived and not failed and not collided and not blocked
        terminated = arrived or failed or collided or blocked
        progress_m = before - distance
        route_m = math.hypot(self.ship[16] - start_x, self.ship[17] - start_y) / 100.0
        cross = _cross_track_m(self.ship[16] / 100.0, self.ship[17] / 100.0, self.destination_m)
        pay_arrival = arrived and not self._arrival_paid
        parts = routing_reward(
            progress_m, cross, float(command[0]), float(command[1]), fuel_t * 1000.0,
            arrived=pay_arrival, failed=failed or collided or blocked,
            fuel_reward_per_kg=self.fuel_reward_per_kg,
        )
        if pay_arrival:
            self._arrival_paid = True
        progress_reward = parts["progress_reward"]
        deviation_reward = parts["deviation_reward"]
        effort_reward = parts["effort_reward"]
        reward = parts["reward"]
        chart_termination = {"land": "land", "shallow": "shallow", "invalid": "chart_invalid", "unknown": "chart_unknown"}.get(chart_now["status"])
        if chart_termination:
            termination = chart_termination
        elif collided:
            termination = "collision"
        elif failed:
            termination = "failure"
        elif arrived:
            termination = "arrived"
        elif truncated:
            termination = "truncated"
        else:
            termination = "running"
        warnings = []
        if chart_now["status"] != "clear":
            warnings.append(chart_now["reason"])
        if decision["status"] not in ("none", "clear"):
            warnings.append(decision["reason"])
        observation = self._observe()
        info = {
            "distance_m": distance,
            "progress_m": progress_m,
            "cross_track_m": cross,
            "effort": float(command[0] ** 2 + command[1] ** 2),
            "progress_reward": progress_reward,
            "deviation_reward": deviation_reward,
            "effort_reward": effort_reward,
            "fuel_reward": parts["fuel_reward"],
            "fuel_kg": parts["fuel_kg"],
            "arrival_reward": parts["arrival_reward"],
            "failure_reward": parts["failure_reward"],
            "reward_name": parts["reward_name"],
            "fuel_reward_per_kg": self.fuel_reward_per_kg,
            "fuel_tph": fuel,
            "heave_cm": heave,
            "pitch_deg": pitch,
            "roll_deg": roll,
            "failure": failed,
            "arrived": arrived,
            "collision": collided,
            "near_miss": near_miss,
            "separation_m": gap,
            "wave_m": self.clock["wave_cm"] / 100.0,
            "inner_dt_s": INNER_DT_S,
            "x_m": self.ship[16] / 100.0,
            "y_m": self.ship[17] / 100.0,
            "heading_deg": self.ship[0],
            "heading_error_rad": self._heading_error(),
            "rudder_deg": self.ship[4],
            "ordered_speed_ms": self.ship[5],
            "surge_ms": self.ship[1] / 100.0,
            "fuel_t": fuel_t,
            "route_m": route_m,
            "termination": termination,
            "chart_status": chart_now["status"],
            "navigable": chart_now["safe"],
            "squat": chart_now["squat"],
            "required_depth_m": chart_now["required_depth_m"],
            "depth_m": chart_now["depth_m"],
            "helm_override": decision["override"] is not None,
            "encounter": decision["kind"],
            "traffic_status": decision["status"],
            "traffic_safe": decision["safe"],
            "cpa_gap_m": decision["cpa_gap_m"],
            "warning": "; ".join(warnings) if warnings else None,
            "hotel_load_kw": HOTEL_LOAD_KW,
        }
        self._distance_m = distance
        return observation, float(reward), bool(terminated), bool(truncated), info

    def _heading_error(self):
        yaw = math.radians(self.ship[0])
        target = math.atan2(self.destination_m[1] - self.ship[17] / 100.0, self.destination_m[0] - self.ship[16] / 100.0)
        return (target - yaw + math.pi) % (2.0 * math.pi) - math.pi

    def _hull_from_ship(self, ship):
        return {
            "x_m": ship[16] / 100.0,
            "y_m": ship[17] / 100.0,
            "heading_deg": ship[0],
            "length_m": ship[7] / 100.0,
            "beam_m": ship[8] / 100.0,
            "surge_cms": ship[1],
            "sway_cms": ship[2],
        }

    def _own_hull(self):
        return self._hull_from_ship(self.ship)

    def _draft_m(self):
        return self.ship[9] / 100.0

    def _chart_at(self, hull, previous=None):
        return water.assess(self.chart, hull, self._draft_m(), self.under_keel_clearance_m, previous)

    def _traffic_decision(self):
        if not self.traffic:
            return {
                "status": "none",
                "safe": None,
                "kind": "none",
                "override": None,
                "cpa_gap_m": None,
                "tcpa_s": None,
                "reason": "no traffic was supplied",
            }
        return encounter_check.decide(self._own_hull(), self.traffic, self.min_separation_m, self.encounter_horizon_s)

    def _traffic_gap_m(self):
        if not self.traffic:
            return None
        own = self._own_hull()
        gaps = []
        for other in self.traffic:
            try:
                gaps.append(separation.separation_m(own, other))
            except (KeyError, TypeError, ValueError):
                return None
        return min(gaps) if gaps else None

    def _raw_distance_m(self):
        return math.hypot(self.destination_m[0] - self.ship[16] / 100.0, self.destination_m[1] - self.ship[17] / 100.0)

    def _observe(self):
        heading_error = self._heading_error()
        service_ms = max(self.ship[15] / 100.0, 0.1)
        distance = self._raw_distance_m()
        cross = _cross_track_m(self.ship[16] / 100.0, self.ship[17] / 100.0, self.destination_m)
        raw = np.array([
            (self.destination_m[0] - self.ship[16] / 100.0) / 8000.0,
            (self.destination_m[1] - self.ship[17] / 100.0) / 8000.0,
            (self.ship[1] / 100.0) / service_ms,
            (self.ship[2] / 100.0) / 4.0,
            heading_error / math.pi,
            self.ship[3] / 0.12,
            self.ship[4] / RUDDER_LIMIT_DEG,
            self.sea["wind_ms"] / 35.0,
            self.sea["current_ms"] / 3.0,
            self.sea["wave_m"] / 6.0,
            cross / 1000.0,
            distance / 8000.0,
        ], dtype=np.float64)
        return np.clip(raw, -1.0, 1.0)


def make_routing_env(**kwargs):
    """Build the routing environment. This is the documented training entry point.

    Import path: `mmg_env:make_routing_env`. Identifier: `MaritimeRouting-v0`.
    No external training package is installed, so this function constructs the
    class directly. It does not register an environment with another framework.
    """
    return MaritimeRoutingEnv(**kwargs)
