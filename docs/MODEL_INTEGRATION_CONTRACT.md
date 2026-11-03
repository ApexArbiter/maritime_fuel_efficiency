# Model integration contract

**Version: 3**

`scripts/mmg_env.py` sets `CONTRACT_VERSION = 3`. Observation length 12 and
action length 2 are unchanged from version 2. Version 3 adds the direct
entry point `make_routing_env`, records that action value 0 is half service
speed, and adds an initial fuel term to the reward. Set
`fuel_reward_per_kg=0` to recover the version 2 reward.

Route telemetry is specified separately in `docs/TELEMETRY_SCHEMA.md`
(schema version 1). It does not change this observation or action contract.

This is the simulator side of the routing interface. It does not define the
incoming network, tensor layout, or training framework. Those fields are
marked pending. The NumPy Soft Actor-Critic agent in `scripts/sac_agent.py`
is a local smoke implementation. It is not the architecture to replace.

## How to create the environment

| Item | Value |
|---|---|
| Identifier | `MaritimeRouting-v0` |
| Import path | `mmg_env:make_routing_env` |
| Call | `env = make_routing_env(destination_m=(...), step_s=1.0, max_steps=300)` |
| Reset | `observation, info = env.reset(seed=None, options=None)` |
| Step | `observation, reward, terminated, truncated, info = env.step(action)` |
| Close | `env.close()`. A later reset or step raises `RuntimeError`. |

No external training package is installed here, so there is no framework
registry. `make_routing_env` constructs `MaritimeRoutingEnv` directly.
`scripts/pretrain_validate.py` reports `entry_points=0` for that reason: the
count is the number of registered trainers, not the number of environments.
Instantiating this class is not the same thing as loading a trained model.

## Simulation

| Item | Value |
|---|---|
| Motion | `mmg_physics.integrate` only. Do not copy the hull equations. |
| Inner step | 0.02 s, unchanged |
| Control step | `MaritimeRoutingEnv.step_s`, default 1.0 s |
| Position | After each 0.02 s step, the environment adds `(forward * surge + right * sway) * dt`. `integrate` itself returns the input x,y. This matches `AFleetShip::ApplyMotion` and `test_turning_circle.step_track`. |
| Units | Positions in the observation are metres. The MMG ship tuple stores centimetres and centimetres per second. |
| Default sea | Wind 4 m/s at 30°, current 0.25 m/s at 40°, waves 0.4 m at 30°. Callers can replace `sea`. |
| Seed | `reset(seed=n)` draws the initial heading from [-15, 15] degrees unless `options["heading_deg"]` is set. The same seed and heading repeat the same observation. |
| Live fleet | Unreal still sends helm from its own autopilot over UDP. This contract does not put the learned action on that socket. **Pending:** whether inference should drive the fleet rudder. |

## Observation

Shape `(12,)`, dtype float64, clipped to [-1, 1]. Order is
`mmg_env.OBSERVATION_FIELDS`.

| Index | Name | Before clipping |
|---|---|---|
| 0 | destination_offset_x | metres east of the ship / 8000 |
| 1 | destination_offset_y | metres north of the ship / 8000 |
| 2 | surge | m/s / service speed |
| 3 | sway | m/s / 4 |
| 4 | heading_error | radians / pi, wrapped to [-pi, pi], target bearing minus heading |
| 5 | yaw_rate | rad/s / 0.12 |
| 6 | rudder | degrees / 35 |
| 7 | wind | m/s / 35 |
| 8 | current | m/s / 3 |
| 9 | wave_height | m / 6 |
| 10 | cross_track | metres / 1000, left of the origin-to-destination line is positive |
| 11 | distance | metres / 8000 |

Direction 0 is +X. Positive yaw and positive rudder turn toward +Y.

## Action

Shape `(2,)`, each value clipped to [-1, 1].

| Index | Name | Mapping |
|---|---|---|
| 0 | rudder | fraction × 35 degrees |
| 1 | ordered speed | -1 is stop (0 m/s), 0 is half service speed, +1 is service speed. Zero is not stop. |

Non-finite values or the wrong shape raise `ValueError` before integration.
A finite value outside [-1, 1] is clipped.

`scripts/inference_adapter.py` is the boundary in front of that check.
`act(observation)` returns two finite numbers. A list, a tuple, or any other
object that supports `len` and indexing is acceptable. No framework, device,
or dtype is required. `guarded_act` clips a finite out-of-range pair. A
non-finite pair, a wrong length, or a raised exception becomes the fallback
`(0, -1)`: rudder amidships and an ordered stop, with status
`invalid_action`. A bad observation is not passed to the model. If `act`
does not return within the timeout (default 0.25 s), the late result is
discarded and the same fallback is used, with status `timeout`.

The default control period is 1.0 s, the environment `step_s`. **Pending:**
whether the architecture owner will emit actions at another period.

`attach_to_fleet` raises. The dummy adapter is not connected to live ship
movement. The existing UDP autopilot stays in place until the architecture
owner says it should be replaced. **Pending:** that decision.

## Reward and ending

The function executed by `step` is `mmg_env.routing_reward`. Its name is
`routing_reward`. An older note that said `reward_function=none` described
the repository before this environment existed. The returned reward is the
value that function returns.

| Term | Definition | Scale note |
|---|---|---|
| progress | `(previous_distance_m - distance_m) / 20` | 20 m of closure is +1 |
| cross-track | `-abs(cross_track_m) / 400` | 400 m off track is -1 |
| effort | `-0.05 * (rudder_fraction² + speed_fraction²)` | both fractions in [-1, 1] |
| fuel | `-fuel_kg * fuel_reward_per_kg` | default coefficient **0.05 per kg**, an initial value that has not been calibrated to a fuel price or a voyage. `fuel_kg` is this step's integral, counted once. |
| arrival | `+10` the first time distance ≤ 150 m without overlap or a chart rejection | later steps do not add +10 again |
| failure, overlap, or chart rejection | `-10` | land, shallow water, and an invalid chart use this same penalty |

`fuel_reward_per_kg=0` removes the fuel term and leaves the other weights as
they were. The coefficient is configurable because no voyage cost data
justifies a tighter number. Passing tests do not make 0.05 optimal.

`terminated` means arrival, a non-finite state, hull overlap, or a blocking
chart result. `truncated` means the step limit was reached first. Truncation
adds no extra reward. They are not the same flag.
`info["termination"]` is `arrived`, `failure`, `collision`, `land`,
`shallow`, `chart_invalid`, `chart_unknown`, `truncated`, or `running`.

There is no extra collision reward on a normal episode. `traffic` defaults
to an empty list. Empty traffic is not a statement that the sea was searched.

## Safety

`hull_separation.separation_m` compares two rectangles in metres. Positive is
a gap. Negative is overlap. Overlap terminates the episode. A gap below 50 m
sets `info["near_miss"]` and does not add a penalty.

The MMG1 request already includes, for every fleet ship, position in
centimetres, heading, surge, sway, yaw rate, rudder, ordered speed, and the
hull dimensions. `scripts/fleet_state.py` reads those hulls and can report
pairwise separation. A sequence that is not newer than the last accepted
sequence raises `StaleFleetState`. A short packet or a non-finite hull raises
`IncompleteFleetState` and does not return a partial fleet.

Shore, depth, and chart obstacles are not in the packet. The parser returns
`obstacles: []` and names those fields in `missing`. The routing environment
still defaults to `traffic=[]` and `chart=None`, and it does not read the
live socket. A supplied chart is a synthetic test fixture unless a real
survey is provided. No survey is in this repository. Squat is not modeled.
`encounter.py` implements a geometric head-on, crossing, and overtaking
subset and sets `full_compliance` to false. This is not COLREG compliance.

**Pending:** a real chart, with datum and coverage, if the model is supposed
to avoid anything other than fleet hulls supplied on MMG1.

## Checkpoint and inference

The smoke agent saves a NumPy `.npz` of its own weights. Loading checks
`obs_dim == 12` and `act_dim == 2`.

**Pending:** the incoming checkpoint path, framework, and loader. Supply an
adapter with `act(observation) -> length-2 finite vector`. Do not require
`sac_agent.py` to host that network.

## Two helms

| Path | What it commands | Status |
|---|---|---|
| Unreal waypoint autopilot | The fleet ship's rudder over UDP. It points the bow at the waypoint. | This is the live helm. |
| `MaritimeRoutingEnv` | The Python episode. It does not send UDP. | Training and offline tests. |
| `baseline_helm.py` | A deterministic policy inside the Python episode. | Offline comparison. |
| `inference_adapter.guarded_act` | Checks one action, then the caller may pass it to `env.step`. | Offline only. `attach_to_fleet` raises. |
| Trained checkpoint and loader | Not in this repository. | **BLOCKED.** |

A test that steps the Python environment with a fixed action does not move
the Unreal ship and does not prove a trained model is loaded.

## Speed words

Surge and sway stored on the ship tuple are body components of the velocity
that advances position. The physics code calls that vector ground velocity.
STW is the magnitude of ground velocity minus the current vector, once.
SOG is the magnitude of the ground velocity. COG is its direction, and it is
null below 0.05 m/s. The Unreal HUD prints surge converted to knots. That
number is not SOG and not STW. See `docs/TELEMETRY_SCHEMA.md`.

## What has been checked, and what has not

1. **Unit and math checks.** Fuel `power_kW * 175 / 3_600_000`. Observation
   divisors. Action endpoints. STW, SOG, and COG for known vectors.
2. **Simulation checks.** The configured turning circle, 960 m ±10% diameter
   and 992 m ±10% advance, and the 0.02 s inner step. These tests show the
   simulator hits its own targets.
3. **Real-vessel checks.** None. Hull dimensions in the fleet are class-typical
   figures, not shipyard data. The 0.55 shaft divisor, the resistance
   coefficient 0.0018, the wind coefficients, and the wave factor 0.35 are
   assumptions inside `mmg_physics.py`. Passing the turning target is not a
   sea trial.

## What the architecture owner provides

1. A checkpoint, its path, and a loader. Required metadata is the contract
   version, observation length 12, and action length 2. Framework and dtype
   stay pending. The loader should implement `act(observation)`.
2. Whether actions are produced at 1 Hz or at another `step_s`.
3. Any obstacle list beyond the hulls already present in MMG1. Shore and
   depth are not available.
4. Whether the fleet UDP autopilot should be replaced. Until that is
   confirmed, inference stays off the live socket.
