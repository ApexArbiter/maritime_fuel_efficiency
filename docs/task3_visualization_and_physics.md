# Task 3 — Realistic ship visualization and simulation testing

The three fleet ships are still driven by `scripts/mmg_physics.py`. The new meshes have no collision and do not change mass, draft, power, or the areas sent to Python. The headless water test still builds the original 16-wave ocean; the richer wave field is applied only after the fleet starts.

## Visual ships

Downloaded hull meshes were not a fit. Free packs that look like cargo ships are the wrong length, or their license does not allow this project. A mesh with hundreds of thousands of triangles would also push this machine’s 16 GB editor cap. The ships are built from engine cubes and cylinders, locked to the class dimensions already used by the physics.

| Ship | LOA | Beam | Keel | Waterline | Deck | Displacement | Engine | Service |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Container ship | 300.0 m | 42.8 m | −14.50 m | 0.00 m | +8.00 m | 145,000 t | 45.7 MW | 22.5 kn |
| Aframax tanker | 245.0 m | 42.0 m | −15.00 m | 0.00 m | +6.00 m | 128,000 t | 13.5 MW | 15.0 kn |
| Panamax bulker | 225.0 m | 32.3 m | −14.20 m | 0.00 m | +7.00 m | 87,000 t | 9.8 MW | 14.5 kn |

These are class-typical full-load figures, not the sea-trial sheet of a named vessel. The actor origin is the midship still-water line. The white stripe is that line. Red below the stripe is antifouling. The log line `WATERLINE` records the keel, the stripe, and the deck for each hull.

The container ship has twelve 40-foot-scale bays and five rows of stacks, an aft deckhouse, and a funnel. The tanker has a low freeboard, deck pipes, six tank domes, a midship manifold, and an aft house. The bulker has seven hatch covers and four cranes. The hull is eighteen slices, narrow at the bow and stern, with a rising sheer, a rounded bilge, and a bulb. That shape is visual. Python still receives the full length, beam, draft, and freeboard in the table.

The live build logged 152 parts on the container ship, 47 on the tanker, and 55 on the bulker. None of those parts collide.

## Ocean

The fleet ocean uses 32 Gerstner components, wavelengths from 8 m to 160 m, a 32° directional spread, and higher steepness on the short waves. The Linux water-mesh cap is raised from 256 tiles to 512 so that field is not coarsened. Wave height and direction are the same numbers sent to Python, so a 0.4 m sea and a 4.0 m sea change both the picture and the forces. The headless water test does not raise the tile cap and does not replace the original 16-wave ocean. Nanite, Lumen, ray tracing, virtual shadows, and volumetric clouds stay off. The recording of this pass had no late frames.

## Same ships, same routes

Each ship starts at its route origin, headed 8° off the first leg, and steers toward the same two waypoints. Arrival is 80 m from the final waypoint. The live run used 8× time and the Python server on UDP port 9001.

Live Unreal run, summer calm (wind 4 m/s at 30°, current 0.25 m/s at 40°, waves 0.4 m):

| Ship | Time | Path | Planned | Mean offset | Max offset | Fuel | Mean speed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Container ship | 318.8 s | 1144 m | 1220 m | 11.0 m | 23.8 m | 0.081 t | 7.0 kn |
| Aframax tanker | 365.2 s | 1156 m | 1234 m | 8.6 m | 17.4 m | 0.048 t | 6.2 kn |
| Panamax bulker | 363.3 s | 1149 m | 1227 m | 9.1 m | 16.6 m | 0.037 t | 6.1 kn |

Live Unreal run, winter storm (wind 22 m/s at 210°, current 1.2 m/s at 130°, waves 4.0 m):

| Ship | Time | Path | Planned | Mean offset | Max offset | Fuel | Mean speed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Container ship | 368.8 s | 1209 m | 1220 m | 40.4 m | 81.7 m | 0.265 t | 6.4 kn |
| Aframax tanker | 569.8 s | 1237 m | 1234 m | 70.1 m | 114.6 m | 0.210 t | 4.2 kn |
| Panamax bulker | 600 s, gate not reached | 1207 m | 1227 m | 73.7 m | 117.8 m | 0.155 t | 3.9 kn |

On that live storm leg the container ship used about 3.3 times the calm fuel and ran 40 m off the line instead of 11 m. The tanker took about half again as long and used about 4 times the fuel. The bulker was still short of the 80 m gate at 10 minutes. While the storm was on screen the container readout was about 2.5 t/h and +3 m of heave, against about 0.5 t/h and a few tenths of a metre in the calm.

The same autopilot and the same `step_once` function, replayed offline at a fixed 0.05 s step (`scripts/voyage_compare.py`):

| Ship | Calm time | Calm fuel | Calm offset | Storm result | Storm fuel | Storm max offset | Storm heave |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Container ship | 210.0 s | 0.048 t | 36 m | no arrival in 600 s | 0.283 t | 578 m | 4.00 m |
| Aframax tanker | 242.4 s | 0.030 t | 27 m | no arrival in 600 s | 0.171 t | 297 m | 4.00 m |
| Panamax bulker | 240.9 s | 0.023 t | 26 m | 381.2 s | 0.116 t | 103 m | 4.00 m |

Calm path length agrees between the live run and the replay (container 1144 m and 1148 m). The live calm clock is longer, and the live calm fuel is higher, because that leg overlapped a screen capture and frames slower than 0.25 s of dilated time were clamped. The storm comparison is more important: at a fixed 0.05 s step the container and tanker leave the route, while the live 8× frames kept those two inside the gate and let the bulker time out. The storm track is sensitive to when the autopilot updates. Treat the live table as what this screen run did, and the fixed-step table as the same equations with a steady clock. Do not treat either table as a ship trial.

## What is checked, and what is still an approximation

Checked in this project:

- Python is the motion source. Unreal sends the hull state and the sea state, and applies the reply. The HUD stays on “MMG physics” while the numbers move.
- Calm path length stays near the planned route, and it matches the offline replay of the same function.
- Heave grows with the commanded wave height: a few tenths of a metre in the 0.4 m sea, and about 3 m on screen in the 4 m sea. The offline sine reaches the full 4.0 m.
- Fuel and leeway rise from the calm preset to the storm preset, on screen and in the replay.
- The visual keel, white stripe, and deck match the draft and freeboard sent to Python. The parts do not collide and do not enter the force calculation.
- The headless water-test ocean is not given the 32-wave fleet spectrum.

Still an approximation:

- The Python step is not a classical MMG model. There is no added-mass matrix and no hull derivatives. Sway relaxes toward the current with an 8 second time constant. Yaw is a Nomoto-style response to rudder angle, plus a small wind term.
- Calm-water resistance uses one coefficient, 0.0018, on the wetted area `length × (beam + 2 × draft) × 0.85`. It is not an ITTC friction line plus a form factor and a residual curve.
- Added resistance in waves is `0.5 × ρ × g × amplitude² × beam × 0.35`, and only for a head sea. It is not a response-amplitude operator and not a measured added-resistance curve.
- Heave, pitch, and roll come from one sine whose length is 90 m. They are not samples of the rendered Gerstner surface, and they do not change the resistance except through the wave height already in that head-sea term.
- Wind is quadratic drag on the freeboard rectangle. The deckhouse is not in the wind area.
- Fuel is useful resistance power times 175 g/kWh, clamped to installed power. There is no shop-test SFOC curve and no auxiliary load.
- The autopilot points the bow at the next waypoint. It does not hold a cross-track. In a 1.2 m/s cross current that is enough to miss the 80 m gate.
- Time acceleration scales the world tick. A dilated step longer than 0.25 s is cut short so the integration stays bounded. A hitch therefore moves the ship less than the wall clock suggests.
