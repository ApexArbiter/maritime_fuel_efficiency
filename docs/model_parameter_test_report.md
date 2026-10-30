# Model and parameter test report

**Final status: PASS, with limitations**

The active runtime model is the MMG ship step in `scripts/mmg_physics.py`, connected to the fleet session over UDP. There is no Gym environment, no SAC network, and no checkpoint. Numerical tests, the water test, and the live preset, pause, time-scale, reset, day/night, and visual-sea checks passed. The previously unverified panel clicks, spring and autumn presets, visual-sea keys, and frame-time sample were exercised on the running viewport. Section 12 records those steps and the measured values.

The drawn swell is still not driven by the physics wave height. That separation is intentional. Gym, SAC, and a checkpoint remain unimplemented. No training was started. `scripts/mmg_physics.py` and the three test modules were unchanged (SHA-256 matched before and after). No checkpoint file exists to overwrite.

## 1. Project and engine

| Item | Value |
|---|---|
| Project root | `/home/user/Projects/maritime_fuel_efficiency` |
| Engine | Unreal Engine 5.8.4, changelist 58902052, branch `++UE5+Release-5.8` |
| Editor | `/home/user/UnrealEngine/UE_5.8.4/Engine/Binaries/Linux/UnrealEditor` |
| Map | `/Engine/Maps/Templates/TimeOfDay_Default` |
| Game mode | `MaritimeGameMode` |
| Desktop | `/home/user/Desktop` (`xdg-user-dir DESKTOP`) |
| Before this audit | Unreal Editor was not running. `mmg_physics.py` was not running. |

The fleet session was started once for the live checks and the recording. It was still running at the end, on Summer calm at 1x, with `mmg_physics.py` listening on `127.0.0.1:9001`.

## 2. Active processes

| Process | Role | Status during the live checks |
|---|---|---|
| `UnrealEditor` | Windowed fleet, 1024×768, `-game` | Running. Log `logs/fleet_demo.log`. |
| `scripts/mmg_physics.py` | UDP MMG step, port 9001 | Spawned by `AFleetEnvironment::LaunchPhysics`. |
| Water-test editor | Headless `-nullrhi -WaterTest`, port 9000 | Ran first, exited 0, then was not left running. |

The fleet does not use port 9000. That socket belongs to the separate water-test bridge in `ShipPawn`.

## 3. What is active

| Component | Path | Status |
|---|---|---|
| MMG step, Nomoto yaw, fuel, environment clamp | `scripts/mmg_physics.py` | Active |
| Fleet ships, HUD, controls, procedural sea | `Source/MaritimeFuelEfficiency/Fleet*.cpp` | Active in the fleet game |
| Water-test ocean actor | `MaritimeGameMode` / Water plugin, hidden in the fleet view | Active for the water test. Hidden while the fleet sea mesh is shown. |
| Turning, fuel, and environment tests | `scripts/test_*.py` | Test-only. They call the MMG functions in-process and do not bind port 9001. |
| Training gate | `scripts/pretrain_validate.py` | Test-only. It does not train. |
| Gym, SAC, Actor/Critic, checkpoints | none | Not implemented. Search of the tree found no `.pt`, `.pth`, `.ckpt`, `.onnx`, `.pkl`, or `.zip` checkpoint. `TRAINING_GATE entry_points=0`. |

## 4. Parameter inventory

### A. MMG ship dynamics

Owner: `step_once` and `integrate` in `scripts/mmg_physics.py`. The fleet sends one packet per frame. Python returns surge, sway, yaw rate, heading, heave, pitch, roll, fuel, and an `ACK1` trailer of the clamped environment.

| Parameter | Value | Unit | Constraint |
|---|---|---|---|
| Substep | 0.02 | s | `integrate` splits any positive `dt`. `dt <= 0` does not advance environment time. |
| Frame step sent by the fleet | `min(DeltaSeconds, 0.25)` | s | `FleetEnvironment.cpp` |
| Water density | 1025 | kg/m³ | constant |
| Air density | 1.225 | kg/m³ | constant |
| Gravity | 9.81 | m/s² | constant |
| SFOC | 175 | g/kWh | `fuel_rate_kg_s = kW * 175 / 3_600_000` |
| Surge drag coefficient | 0.0018 | — | on wetted area |
| Sway drag coefficient | 0.85 | — | on length × draft |
| Wind surge / sway coefficients | 0.8 / 0.9 | — | frontal and lateral area |
| Wave resistance factor | 0.35 | — | head seas only, `max(0, -cos(wave_deg - yaw))` |
| Surge / sway added-mass factors | 1.08 / 1.5 | — | |
| Yaw | first-order Nomoto | 1/s, s | `K'`, `T'` from the 960 m / 992 m reference |
| Reference hull | 300 m, 15.5 kn, 35° rudder | | steady diameter 960 m, advance 992 m |
| Yaw-rate clamp | ±0.12 | rad/s | |
| Sway clamp | ±400 | cm/s | |
| Wave length | 90 | m | `k = 2π/9000 cm`. Period is not an input. |
| Directions | degrees from +X toward +Y | deg | wrapped to `[0, 360)` |

Wind, current, and wave packets are clamped, not rejected, when finite but out of range: wind 0–35 m/s, current 0–3 m/s, waves 0–6 m. A non-finite environment, `dt`, or simulation time returns `REJ1` and does not step.

Fleet hulls (`FleetShip.cpp`, full-load class figures):

| Hull | Length | Beam | Draft | Freeboard | Displacement | Power | Service speed |
|---|---|---|---|---|---|---|---|
| Container ship | 300 m | 42.8 m | 14.5 m | 8 m | 145,000 t | 45.7 MW | 22.5 kn |
| Aframax tanker | 245 m | 42.0 m | 15.0 m | 6 m | 128,000 t | 13.5 MW | 15.0 kn |
| Panamax bulker | 225 m | 32.3 m | 14.2 m | 7 m | 87,000 t | 9.8 MW | 14.5 kn |

Wetted area is `L * (B + 2T) * 0.85`. The hull meshes do not use a physics body. Motion comes from the UDP reply.

### B. Environment

Season presets are the only weather states. They set wind, current, waves, month, hour, sun, and exposure. `F5` / `F6` / `F7` change the visual sea only and do not write `WaveM`.

| Preset | Wind | Current | Waves | Hour | Exposure |
|---|---|---|---|---|---|
| Summer calm | 4 m/s at 30° | 0.25 m/s at 40° | 0.4 m at 30° | 13:00 | +0.25 |
| Spring tide | 8 m/s at 110° | 1.40 m/s at 120° | 1.3 m at 110° | 09:00 | +0.05 |
| Autumn gale | 18 m/s at 200° | 0.70 m/s at 190° | 2.8 m at 200° | 16:00 | −0.35 |
| Winter storm | 22 m/s at 210° | 1.20 m/s at 130° | 4.0 m at 200° | 20:30 | −1.05 |

Time scale is world time dilation, clamped to 0–30. It does not change the 0.02 s physics substep. Pause sets dilation to 0 and skips the physics exchange.

Visible sea mesh: disc color `(0.014, 0.062, 0.098)`, roughness `0.58`, shade `1.65`. Default visual preset is moderate (amplitude about 14–72 cm). The engine ocean material is written and then hidden in the fleet view: albedo `(0.007, 0.028, 0.040)`, scattering `(0.11, 0.30, 0.46)`, absorption `(42, 14, 4.5)`.

### C. Reinforcement learning

Not implemented. No observation space, action space, reward, termination condition, network, optimizer, or checkpoint. `test_fuel_units.py` records `gym=none` and `reward_function=none`. The historical −2327 figure is not a live reward.

## 5. Tests and results

Commands were run from `scripts/` with `PYTHONDONTWRITEBYTECODE=1`. `voyage_compare.py` was not run.

| Check | Method | Result |
|---|---|---|
| Turning circle, straight course, smaller rudder | `python3 -m unittest test_turning_circle` | **PASS.** Steady diameter 961.544 m (limit 864–1056), advance 991.963 m (limit 892.8–1091.2), tactical diameter 1192.318 m, approach 15.500 kn. |
| Fuel units and UDP reply | `python3 -m unittest test_fuel_units` | **PASS.** 1000 kW → 0.0486111111 kg/s and 175 kg/h. |
| Environment clamp, rejection, current, waves, substep, presets | `python3 -m unittest test_environment_controls` | **PASS.** 10 tests. |
| Combined unit run | the three modules together | **PASS.** 19 tests in 1.885 s, exit 0. |
| Training gate | `python3 pretrain_validate.py` | **PASS.** `entry_points=0`. No training call. |
| In-process self-test | `python3 mmg_physics.py --self-test` | **PASS.** Calm heave peak 0.40 m; gale heave peak 4.00 m and higher sway and fuel. |
| Water test | `scripts/run-water-test.sh` | **PASS.** `WATER TEST PASS`, editor exit 0. |
| Live physics link | fleet log after launch | **PASS.** `MMG APPLIED wind 4.00 m/s at 30, current 0.25 m/s at 40, waves 0.40 m at 30`. |
| Live winter storm | V key while the fleet window was focused | **PASS.** Ack `wind 22.00 m/s at 210, current 1.20 m/s at 130, waves 4.00 m at 200`, sim 293.9 s. HUD heave about +3.5 m. |
| Live return to summer | Z key | **PASS.** Ack returned to 4.00 / 0.25 / 0.40. |
| Live pause and resume | Space, twice | **PASS.** Log `ENV paused`, then `ENV running 1x`. HUD showed PAUSED and the button label Run. |
| Live 5× then 1× | keys 5 and 1 | **PASS.** Log `ENV time scale 5x`, then `ENV time scale 1x`. Simulation time advanced from about 318 s to about 404 s across that interval, and the ships moved farther along their tracks. |

**Failed: 0** in that first session. The items below were open at that point. Section 12 closed them on the relaunched process, with no further restart.

### Closed by the follow-up in section 12

- Mouse clicks on every panel button, including all four weather presets, pause, resume, 1x/5x/10x/20x, reset, and the wind, current, and wave nudges.
- Spring tide and autumn gale on the live viewport, with both the requested line and the MMG acknowledgement.
- `F5` / `F6` / `F7`, then a return to the lit view. Physics wave height stayed 0.40 m.
- Reset ships.
- Day/night cycle, including an hour change while the simulation was running.
- Numeric frame time from the engine log frame index, and GPU samples from `nvidia-smi`.

### Not implemented

- Gym environment, SAC actor/critic, checkpoints, inference.
- Clear, cloudy, and rain as forces.
- A wave-period control. Wavelength stays 90 m.
- Drawn swell amplitude that follows the physics wave height. Winter changes sun and exposure, so the light on the water changes. The mesh amplitude follows the visual preset.

## 6. Log findings

- Fleet: `ENV CONTROLS ready`, then the applied-value lines above. No physics disconnect during the live checks.
- Water test: `WATER TEST PASS`. The `LogTemp: Error test` lines in that launch are the engine’s own error-system self-check, not a failed water assertion.
- The previous `logs/fleet_demo.log` and `logs/ue_water_test.log` were copied to the demo folder before those working logs were replaced by this run.

## 7. Performance

Measured on the follow-up session while the fleet window was rendering at 1024×768. The bracketed frame index in `logs/fleet_demo.log` is the engine frame counter modulo 1000. Two unpaused windows:

| Window | Frames | Elapsed | FPS | Frame time |
|---|---|---|---|---|
| 16:31:50.558 `[230]` to 16:31:53.662 `[355]`, mostly at 5x | 125 | 3.104 s | 40.27 | 24.83 ms |
| 16:36:24.781 `[9]` to 16:36:27.948 `[145]`, mostly at 20x | 136 | 3.167 s | 42.94 | 23.29 ms |

A longer stretch from 16:31:27.524 `[359]` to 16:31:46.788 `[78]`, across the preset clicks, was 719 frames in 19.264 s, 37.32 fps, 26.79 ms. Time dilation did not change the render rate. The capture files are 8 fps screen recordings, not the engine rate.

`nvidia-smi` on the GeForce RTX 5060 Ti:

| When | GPU util | Memory util | Memory used | Graphics clock | Power | Temperature |
|---|---|---|---|---|---|---|
| 16:32, shader-complexity view | 14% | 1% | 1494 MiB | 2752 MHz | 27.01 W | 31 °C |
| 16:36, lit view while running | 19% | 1% | 1502 MiB | 2745 MHz | 35.39 W | 41 °C |

No `stat unit` overlay and no `PROFILEGPU` dump were taken. The numbers above are the engine frame counter and `nvidia-smi`, not a GPU pass trace.

## 8. Errors and handling

The first screen capture could not deliver keys because the window manager did not give the game keyboard focus. Those frames were not used as `test.mp4`. The fleet process was left running. A second capture, after the game window was actually focused, recorded the winter-storm acknowledgement, the restore, the pause, and the 5× change. The simulation was put back to Summer calm at 1× before the recording ended.

## 9. Evidence

| Evidence | Path |
|---|---|
| Video | `/home/user/Desktop/test.mp4` |
| Unit tests | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_unittest_log.txt` |
| Training gate | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_training_gate_log.txt` |
| Self-test | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_self_test_log.txt` |
| Water test | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_water_test.log` |
| Live preset and time log | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_runtime_log.txt` |
| Summer frame | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_test_summer.png` |
| Winter frame | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_test_winter.png` |
| Pause frame | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_test_paused.png` |
| 5× frame | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_test_5x.png` |
| Test output frame | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_test_results.png` |
| Restored frame | `/home/user/Desktop/Maritime_AI_Demo/model_parameter_test_restored.png` |
| Follow-up control video | `/home/user/Desktop/ui_control_verification.mp4` |
| Follow-up lit visual video | `/home/user/Desktop/ui_visual_sea_lit.mp4` |
| Follow-up log excerpt | `/home/user/Desktop/Maritime_AI_Demo/ui_verify_runtime_log.txt` |
| Follow-up frames | `/home/user/Desktop/Maritime_AI_Demo/ui_verify_*.png` |

`test.mp4` is 97.75 seconds, 1024×768, 12 fps, 84,717,532 bytes. The player stayed open, and frames decoded from the file show Summer calm at the start, the 19-test OK summary in the middle, and Summer calm at 1× at the end. The ships are farther along their tracks at the end than at the start. Simulation time on those frames moves from about 282 s to about 404 s. That file was not overwritten.

`ui_control_verification.mp4` is 51.375 seconds, 1024×768, 8 fps, 22,363,335 bytes, 411 decoded frames. The player stayed open (`timeout 8` exit 124). The first decoded frame is the live ocean. A middle frame is the engine shader-complexity view entered by F5. The last decoded frame is still that view.

`ui_visual_sea_lit.mp4` is 19.875 seconds, 1024×768, 8 fps, 20,837,659 bytes, 159 decoded frames. The player stayed open the same way. The first and last decoded frames are the lit ocean, sky about `(238, 243, 242)`.

## 10. Source control

This audit and the follow-up updated this report only. They did not edit `mmg_physics.py`, the test modules, hydrodynamic coefficients, fuel, turning, or the fleet sources. SHA-256 of `scripts/mmg_physics.py` after the follow-up was `c3137932fb345d9e2373628de40f9df507ab5f72893b5ad720d2379fef3aface`, the same value as before. The working tree was already dirty before this audit (fleet sources, config, and scripts). No commit was made. No checkpoint was written. No training was started.

## 11. Count

| | |
|---|---|
| Passed | 48 (the original 29, plus 19 follow-up runtime checks in section 12) |
| Failed | 0 |
| Not verified | none of the controls listed in the follow-up request |
| Not implemented | Gym, SAC, checkpoints, wave period, clear/cloudy/rain, swell mesh driven by physics wave height |

## 12. Follow-up runtime verification

The fleet window from the first audit had been closed by `SDL_EVENT_QUIT` (return code 0, not a crash). It was relaunched once. Every check in this section used that process, Unreal Editor PID 1089029 and `mmg_physics.py` PID 1089560, without another restart. The window was focused by a KWin script that minimized the IDE, because otherwise mouse and key events went to the IDE and produced no log lines. Cursor was restored afterward. The session was left on Summer calm, 1x, moderate visual, day/night off, and running.

Clicks are root-window pixels. The panel origin on that window is x=690. Button centers that produced log lines: Summer `(755, 96)`, Spring `(936, 96)`, Autumn `(775, 120)`, Winter `(921, 120)`, time row y=298 at x=711, 764, 818, 870, pause `(924, 298)`, reset `(750, 330)`. A first pause click at `(960, 298)` missed the 52-pixel button. `F5`, `F6`, `F7`, and `N` are keys, not panel buttons.

### Weather presets

Each row is one mouse click. The request is the `ENV PRESET` line. The acknowledgement is the next `MMG APPLIED` line.

| Click | Requested | Acknowledged | Sim time |
|---|---|---|---|
| Summer calm | wind 4.0 m/s at 30, current 0.25 m/s at 40, waves 0.4 m at 30, hour 13.0 | wind 4.00 at 30, current 0.25 at 40, waves 0.40 at 30 | 412.6 s |
| Spring tide | wind 8.0 m/s at 110, current 1.40 m/s at 120, waves 1.3 m at 110, hour 9.0 | wind 8.00 at 110, current 1.40 at 120, waves 1.30 at 110 | 415.4 s |
| Autumn gale | wind 18.0 m/s at 200, current 0.70 m/s at 190, waves 2.8 m at 200, hour 16.0 | wind 18.00 at 200, current 0.70 at 190, waves 2.80 at 200 | 418.1 s |
| Winter storm | wind 22.0 m/s at 210, current 1.20 m/s at 130, waves 4.0 m at 200, hour 20.5 | wind 22.00 at 210, current 1.20 at 130, waves 4.00 at 200 | 420.8 s |

**PASS.** HUD titles matched those presets. Water pixel `(200, 500)` and sky pixel `(400, 180)`:

| Preset | Water RGB | Sky RGB |
|---|---|---|
| Summer calm | 47, 72, 102 | 236, 240, 239 |
| Spring tide | 45, 80, 128 | 230, 238, 242 |
| Autumn gale | 39, 66, 109 | 233, 240, 243 |
| Winter storm | 18, 48, 104 | 208, 227, 238 |

The presets change sun color, exposure, and hour. They do not rewrite the sea-mesh color `(0.014, 0.062, 0.098)`. The darker winter water is that lighting change. Frames: `ui_verify_summer.png`, `ui_verify_spring.png`, `ui_verify_autumn.png`, `ui_verify_winter.png`.

### Panel nudges, time scale, pause, and reset

Starting from Summer calm, each nudge was one click and each acknowledgement changed only the nudged value:

| Click | Acknowledged change |
|---|---|
| Wind + / Wind − | 5.00 m/s, then 4.00 m/s, direction stayed 30 |
| Wind dir + / dir − | direction 40, then 30 |
| Current + / Current − | 0.45 m/s, then 0.25 m/s |
| Current dir + / dir − | direction 50, then 40 |
| Wave + / Wave − | 0.80 m, then 0.40 m |
| Wave dir + / dir − | direction 40, then 30 |

**PASS.**

Mouse time scale, in order: `ENV time scale 5x`, `1x`, `10x`, `20x`, `1x`. **PASS.**

Pause at `(924, 298)` logged `ENV paused`. The HUD read `SUMMER CALM PAUSED` and the button label changed to Run. Simulation time stayed 734.8 s on the next frame. A later pair on the same button logged `ENV paused` at 16:37:57.904 and `ENV running 1x` at 16:37:58.827. One resume click in between missed because a screenshot notification covered the window. The successful pair is the result. **PASS.**

Reset at `(750, 330)` logged `ENV reset on custom`. The following frame shows the ships back near the origin. **PASS.** Summer calm was clicked again afterward. The values were already the summer values, so no new `MMG APPLIED` line was required. The request line was logged.

### Visual sea and physics wave height

These stay separate, and they should stay separate.

`WaveM` is the physical input. The fleet sends it in the UDP packet, and `step_once` uses it for head-sea wave resistance and for heave, pitch, and roll. Those forces are real. The visible disc does not use `WaveM` for its vertex height. Height comes from the visual preset: calm 8–28 cm, moderate 14–72 cm, rough 22–130 cm. `FoamScale = clamp(0.55 + WaveM * 0.18, 0.45, 1.7)` changes foam opacity on the engine water body, which the fleet view hides. Coupling the drawn amplitude to `WaveM` would rebuild the mesh scale and would make a visual key change the physics input. That was not done. No MMG coefficient was edited.

Runtime proof, after a Summer click had set waves to 0.40 m:

| Key | Visual log | Physics |
|---|---|---|
| F5 | calm visual, 8 components, amplitude 8–28 cm, summed crest 135 cm | stays 0.40 m, no new `MMG APPLIED` |
| F7 | rough visual, 14 components, amplitude 22–130 cm, summed crest 934 cm | stays 0.40 m |
| F6 | moderate visual, 12 components, amplitude 14–72 cm, summed crest 461 cm | stays 0.40 m |

The same moderate line, amplitude 14–72 cm, was logged while the acknowledged physics wave was 0.40 m, 1.30 m, 2.80 m, and 4.00 m. **PASS** for the separation.

F5 is also the engine debug binding `viewmode shadercomplexity` in `Engine/Config/BaseInput.ini`. The first F5 press turned the viewport red (`MaxShaderComplexityCount=2000`) at the same time as it set calm visual. F6 and F7 are not debug view keys. F3 is `viewmode lit` and restored the picture. A second pass pressed F5, then F3, then F7, then F6. The lit HUD read calm visual, rough visual, then moderate visual, with applied wave 0.4 m on each frame. At this camera distance the stills do not show an obvious swell-height change. The engine's own amplitude lines are the measurement. **Limitation:** F5 still opens the shader-complexity view until F3 is pressed. The project input file was not changed, because that change would not apply to the running process and the process was not restarted.

### Day/night

`N` logged `ENV day/night cycle on`, then `off`. While running, the HUD moved from 13:00 to 13:50 during the 3.2 s the cycle was on. That matches the tick, which adds `0.25` hours per real second only when the simulation is not paused. A toggle made while paused showed the `day/night cycle` label and left the hour at 13:00. No `MMG APPLIED` line was produced. Summer calm was clicked afterward and the request line returned hour 13.0. **PASS.**

### Log

From this process, after startup:

- `MMG physics has not answered yet` at 16:25:33, 16:30:14, and 16:33:44. The link recovered. `MMG physics connected` followed the third warning, and `MMG APPLIED` lines continued after all three. Ships reached later waypoints.
- `LogConsoleManager` warning: 31 failed lookups of `r.EyeAdaptation.ExposureCompensation`. Exposure still changed with the presets. This is an engine console-variable warning, not a rejected environment packet.
- `LogRenderer` warning that screen-space global illumination is deprecated. No Nanite, Lumen, or ray tracing was enabled.
- Startup `LogTemp: Error test` lines are the engine error-system self-check.
- No `REJ1`, no fatal, and no rendering device lost.

**PASS** for the communication and rendering check, with those warnings left as engine noise.
