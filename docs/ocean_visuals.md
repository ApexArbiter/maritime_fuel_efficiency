# Visual ocean

This note describes the fleet presentation sea added on 28 Oct 2026. It does not replace the earlier voyage tables in `docs/task3_visualization_and_physics.md`.

The wave shapes in the fleet view are a visual preset. They are not a Beaufort scale, and they were not checked against a measured sea spectrum.

## What the fleet camera shows

The built-in water mesh stayed visually flat in this project. Logged Gerstner components did not move the open-water pixels. The engine fades those waves out when the depth capture has no seabed, and this map has no landscape to provide that depth.

The fleet view draws its own sea. An earlier version of that mesh used a square skirt: wave height was cut off with a square distance test and the outer edge dropped. That crease is the sharp rectangle in `Maritime_AI_Ocean_Demo.mp4`. The skirt is gone. The mesh is now a disc, 4.4 km across, with an even 129 by 129 grid so the water beside the ships is about 34 m between vertices. Five sine swells run in different directions. Their shading uses the slope of those sines. Amplitude eases off only near the circular rim. The engine water actor stays hidden in the fleet demo so it cannot draw a second plane through the disc.

F5, F6, and F7 still select calm, moderate, and rough appearance. They do not change the wave height sent to Python.

The water-test path does not build this mesh and does not disable the engine water. Its 16-wave Gerstner setup is unchanged. The headless check on 28 Oct 2026 still printed `WATER TEST PASS`.

## Presets

F5, F6, and F7 select calm, moderate, and rough appearance. The default is moderate. The on-screen line names the preset and still shows the physics wave height separately.

These keys change visual wavelength, spread, steepness, roughness, foam scalars, and the sine-mesh amplitude. They do not change wind, current, or `WaveM`. The UDP packet still sends `WaveM * 100` centimetres. Summer calm remains 0.4 m on the wire.

## Wake and waterline

Each ship has ten flat pieces created once, with no collision. Two sit at the bow shoulders and eight overlap along the stern. Length, spread, and fade follow the surge already produced by Python, and they hide below about 0.4 m/s. They are still separate pieces. In a wide view one of them can read as a short board on the water.

The hull origin is still the still-water line. Python heave is still the only vertical motion of the actor. The visual sea moves around that line. A crest can cover the boot stripe. That offset is not written back to Python.

## What was not changed

`scripts/mmg_physics.py`, the turning-circle test, the fuel-unit test, and the training gate were not edited for this work. No training was started.

## Checks run after the visual change

From `scripts/`, with bytecode writing disabled:

```bash
python3 -m unittest -v test_turning_circle test_fuel_units
python3 pretrain_validate.py
```

Result: 9 tests OK. Steady diameter 961.544 m, advance 991.963 m, approach 15.500 kn. At 1,000 kW the rate is 0.0486111111 kg/s and one hour is 175 kg. Training gate passed with `entry_points=0`.

```bash
scripts/run-water-test.sh
```

Result: `WATER TEST PASS` in `logs/ue_water_test.log`.

The fleet screenshots after the disc change were taken with `scripts/run-fleet-demo.sh -ShipShots`. The log printed `VISUAL SEA MESH 129 x 129` and `SHIPSHOT COMPLETE 8`. The editor exited 0. The same water-test command printed `WATER TEST PASS` again. No GPU-utilisation sample was recorded during that run.

## Sea color, 29 Oct 2026

The distant swell band uses the disc material color. That color stays `(0.014, 0.062, 0.098)`. Roughness is `0.58` and slope shading is `1.65`, so the crest highlight is broader than the earlier `3.6` shade. Two extra slopes affect the normal only and do not move the surface. Sine amplitudes, wavelengths, and speeds are the same. The four season presets still change sun color, brightness, exposure, and the physics wave height. They do not replace the sea color with one fixed blue.

A same-camera horizon frame from the summer-calm preset measured the distant band at luminance 172 before and 161 after. The water beside the hull stayed near luminance 53. Engine-water albedo writes did not move those near pixels. There is no separate clear, cloudy, or rain state.

## Limits

The disc removes the square crease. Close alongside the hull, the water can still look smooth because the swell is long and the material is a plain lit color. The wake is a bounded row of flat pieces, not a continuous foam sheet. Engine water reflections stay off in the fleet view.
