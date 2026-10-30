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

The machine profile in `Config/` keeps the RTX 5060 Ti on Vulkan. The picture is a medium preset for this 1024×768 desktop: temporal anti-aliasing, screen-space reflections and global illumination, medium shadows, bloom, ambient occlusion, and light shafts. Nanite, Lumen, ray tracing, virtual shadows, volumetric fog, and volumetric clouds stay off. The texture pool is 1024 MB, with one shader-compile worker. Selkies, x0vnc, and guacd stay on CPUs 0–1 with a protected memory floor. Unreal is limited to the other cores, idle I/O priority, and a 16 GB soft / 24 GB hard memory cap.

The NVIDIA driver in use is 580.196.07. The editor selects the RTX 5060 Ti over the software renderer.

## Water

Built-in plugins only: Water, Buoyancy, Water Advanced, Niagara Fluids, Niagara, Landmass, Sun Position, and GeoReferencing. The ocean is a 16 km Gerstner water body. The ship hull does not simulate physics. Five pontoons hold it, and a UDP socket on port 9000 is the motion bridge.

Headless check:

```bash
scripts/run-water-test.sh
```

The log is `logs/ue_water_test.log`. A passing run prints `WATER TEST PASS` after about 12 seconds of play: the waves vary, the 200 kg cube stays up, the 3000 kg cube sinks, and the ship stays near the still-water line.

## Fleet ships and the environment

The fleet is three class-typical hulls: a 300 m container ship, a 245 m Aframax tanker, and a 225 m Panamax bulker. Python in `scripts/mmg_physics.py` is the motion source, on UDP port 9001. The meshes are visual only. `docs/task3_visualization_and_physics.md` records the dimensions, the calm and storm voyage numbers, and which parts of the force model are checked approximations. `scripts/voyage_compare.py` replays the same step at a fixed clock.

The fleet view uses a separate visual sea. F5, F6, and F7 select calm, moderate, and rough appearance. Those keys do not change the wave height sent to Python. `docs/ocean_visuals.md` describes the mesh, the wake, and what was actually verified.

## Auto-commit

`scripts/auto-commit.sh` commits local changes and pushes `main` to GitHub. A snapshot survives an instance failure only after a successful push.

Log: `.git/auto-commit.log`
