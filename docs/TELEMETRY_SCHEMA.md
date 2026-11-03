# Route telemetry schema

**Schema version: 1.** Name: `maritime_route_telemetry`.

This layer reads the routing environment and the MMG ship tuple. It does not
integrate motion, does not recompute resistance or shaft power from the hull
equations, and does not change observation length 12 or action length 2.

## Files

`scripts/route_telemetry.py` writes three files per run, plus a status file.
Names include the run id, route id, UTC stamp, and a random token. An existing
file is not overwritten unless `overwrite=True`.

| File | Role |
|---|---|
| `*.csv` | One header, then one row per sample. A missing value is an empty field. |
| `*.jsonl` | One JSON object per line. A missing value is `null`. |
| `*.summary.json` | Totals and coverage. This is not a second copy of every sample. |
| `*.status.txt` | `partial` until `finalize`. Then `complete`, `partial` for an interrupted route, or `failed`. |

Samples are appended and flushed. The recorder keeps running totals only, so
the sample list is not held in memory. A repeated `step_index` is ignored, so
a retry does not add fuel or distance again. If the directory cannot be
created, `record_sample` returns `export_failed` and does not raise.

The Python process writes these files. Unreal's game thread does not.

## Speed definitions

The frame is the simulation frame: 0 degrees is +X, positive toward +Y.
Angles are wrapped to [-180, 180] with `mmg_physics.wrap_deg`.
Inputs that are centimetres per second are converted once, to metres per second.

| Quantity | Definition |
|---|---|
| Heading | Bow direction, `ship[0]`. |
| Ground velocity | Body surge and sway rotated by heading. This is the vector `advance_position` adds. |
| SOG | Magnitude of that ground velocity. |
| COG | Direction of that ground velocity. Null when SOG is below 0.05 m/s. |
| Current | `mmg_physics.direction(current_deg, current_cms)`. |
| Water-relative velocity | Ground velocity minus the current vector, same frame and units. |
| STW | Magnitude of the water-relative velocity. |

Heading is not COG. Current speed is not added to STW as a scalar.
The stored surge and sway are the body components of the velocity that
advances position. In `step_once` that vector is named `ground`. Water-relative
velocity is that vector minus the current vector, once. The sway equation also
relaxes sway toward the lateral component of the current, so an abeam current
gradually appears inside sway and therefore inside SOG. A head current does
not get added to surge; it changes surge only through water-relative resistance.
Telemetry must not subtract the current a second time, and position advance
must not add it on top of surge and sway.

If the current fields are absent, SOG and COG can still be set and STW is null.
If heading or body velocity is non-finite, SOG, COG, and STW are null.
A stale sample leaves all of those speeds null. None of these cases is stored as zero.

There is no latitude or longitude. Those fields stay null. RPM and throttle
are not on the ship tuple and stay null. Ordered speed and rudder are the
actuator values the environment stored.

## Power and fuel

`step_once` computes shaft watts, caps them by installed power, and returns
fuel as tonnes per hour:

`fuel_tph = fuel_rate_kg_s(shaft_kW) * 3.6`

`fuel_rate_kg_s(power_kW) = power_kW * 175 / 3_600_000`

Telemetry inverts that identity. It does not rebuild the resistance model.

| Check | Value |
|---|---|
| 100 kW | 0.0048611111 kg/s, 17.5 kg/h |
| 1,000 kW | 0.0486111111 kg/s, 175 kg/h |

`power_type` is `shaft`. `power_status` and `fuel_status` are `estimated`
when the returned tonnes-per-hour value is finite and non-negative.
A missing rate is `unavailable`. A negative or non-finite rate is `invalid`,
and both the rate and the shaft kilowatts stay null.

The environment adds `step_fuel_tonnes(fuel_tph, dt)` across the 0.02 s
substeps of one control step and reports that sum as `fuel_t` in tonnes.
A negative or non-finite rate contributes zero.
Telemetry adds `fuel_t * 1000` kilograms once for that step index. It does
not multiply the last substep rate by the control period, and it does not
assume the control period is one second. The rate field is the last substep's
tonnes per hour. The cumulative field is the step integral.

## Route summary

`finalize` records status, simulation start and end, elapsed simulation time,
distance travelled (sum of each step's `route_m`, once), waypoints completed
or missed for the single destination, cumulative estimated fuel, the fraction
of samples that carried a fuel integral, and mean, minimum, and maximum only
for series that had at least one finite sample. Geographic distance is not
computed from X and Y.

## What this project still does not have

Real-model checkpoint, framework, dtype, and loader. See
`docs/MODEL_INTEGRATION_CONTRACT.md`. `scripts/inference_adapter.py` refuses
`attach_to_fleet`. The UDP autopilot remains the live helm.

MMG1 carries ship position, heading, length, and beam.
`scripts/fleet_state.py` parses that and rejects a stale sequence, a short
packet, and a non-finite hull. Shore, depth, and chart obstacles are not in
the packet. The routing environment still starts with no traffic. Parsing
and pairwise rectangle separation are not COLREG and are not live-socket
validation.

Training the external architecture is **BLOCKED**. The gate in
`scripts/pretrain_validate.py` reports `entry_points=0` when no Python file
is named like a trainer and no file mentions a training-framework call.
`mmg_env.make_routing_env` is the direct constructor for `MaritimeRouting-v0`.
It is not registered with an external training package, and none is installed.
The local NumPy smoke agent is not that architecture.

The Unreal HUD source labels surge, STW, SOG, COG, and heading separately.
Surge is the body-frame longitudinal speed in knots. STW and SOG use the
same ground and water-relative vectors as `kinematic_speeds`, with the
existing knot factor 1.943844. COG is shown only when SOG is at least
0.05 m/s, and STW is shown only when the applied current is finite.
Missing, stale, or non-finite samples read `N/A`. The passage line still
shows destination distance, fuel tonnes per hour, heave, leeway, and rudder.
This schema describes the source. It does not claim the on-screen HUD was viewed.
