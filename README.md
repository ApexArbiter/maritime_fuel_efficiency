# Maritime fuel efficiency

Unreal project and datasets for this machine. The precompiled engine is installed separately and is not stored in git.

## Layout

| Path | What goes here |
| --- | --- |
| `MaritimeFuelEfficiency.uproject` | Open this in the editor |
| `Content/` `Source/` `Config/` | Unreal project files. These are committed. |
| `data/` | Fuel, voyage, and simulation datasets. These are committed. |
| `docs/` | Notes and references |
| `~/UnrealEngine/UE_5.8.4` | Unreal Engine 5.8.4. This folder is outside the repo. |

Regenerated editor output is intentionally not committed: `Binaries/`, `Intermediate/`, `DerivedDataCache/`, `Saved/`, and `Build/`. Put anything that must survive an instance restart in `Content/`, `Source/`, `Config/`, or `data/`.

## Editor

Launch this project with `scripts/launch-editor.sh`.

The machine profile baked into `Config/` is an RTX 5060 Ti with 16 GB of memory and a 5-core Xeon W-2133: Vulkan, Nanite, hardware Lumen, an 8 GB texture pool, Epic scalability, and four shader-compile cores.

The NVIDIA driver in use is 580.196.07. The editor selects the RTX 5060 Ti over the software renderer.

## Water

Built-in plugins only: Water, Buoyancy, Water Advanced, Niagara Fluids, Niagara, Landmass, Sun Position, and GeoReferencing. The ocean is a 16 km Gerstner water body. The ship hull does not simulate physics. Five pontoons hold it, and a UDP socket on port 9000 is the motion bridge.

Headless check:

```bash
scripts/run-water-test.sh
```

The log is `logs/ue_water_test.log`. A passing run prints `WATER TEST PASS` after about 12 seconds of play: the waves vary, the 200 kg cube stays up, the 3000 kg cube sinks, and the ship stays near the still-water line.

## Auto-commit

`scripts/auto-commit.sh` commits local changes and pushes `main` to GitHub. A snapshot survives an instance failure only after a successful push.

Log: `.git/auto-commit.log`
