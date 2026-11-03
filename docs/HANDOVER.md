# Handover

This file is the start here for a new machine. The GitHub repo is the copy that survives. Generated Unreal output and the GitHub token do not.

Remote: `https://github.com/ApexArbiter/maritime_fuel_efficiency.git`  
Branch: `main`  
Snapshot this handover follows: `56c0814` (shared routing contract, telemetry, and fleet helm).

Clone `main` and use it as-is. Do not force-push. A normal push is rejected if `origin/main` has commits this machine does not have; fetch and merge those first.

## What is already on GitHub

The project is source, config, and data. There is no `Content` library of meshes or maps.

| Path | Role |
| --- | --- |
| `MaritimeFuelEfficiency.uproject` | Linux project. Engine association `5.8`. Open this. |
| `Source/MaritimeFuelEfficiency/` | Game module. Ocean, fleet, HUD, and the water test are spawned in C++. |
| `Config/` | Input, engine, editor, and scalability settings. |
| `scripts/` | MMG physics, routing environment, tests, and launch scripts. |
| `docs/` | Contracts, telemetry schema, voyage notes, ocean notes, and `fleet_navigation.mp4`. |
| `data/task3_voyage_comparison.txt` | Voyage comparison table. |
| `.gitattributes` | LFS patterns for future binary assets. |
| `.gitignore` | Keeps generated output and secrets off GitHub. |

`Content/` is only `.gitkeep`. The fleet demo and the water test open the engine template `/Engine/Maps/Templates/TimeOfDay_Default` and spawn actors from `AMaritimeGameMode`. A missing `Content` asset is not a failed clone.

The recording `docs/fleet_navigation.mp4` is about 8.9 MB and is stored as a normal git blob. A clone does not need Git LFS to receive it.

## What is not in the repo

Leave these off GitHub.

| Item | Why |
| --- | --- |
| `/home/user/UnrealEngine/UE_5.8.4` | Precompiled engine. `scripts/launch-editor.sh` looks at this path. It is outside the repo. |
| `.env` | One line, `GITHUB_TOKEN=...`. `scripts/auto-commit.sh` reads it for `git push`. Copy it onto the new machine by hand. |
| `Binaries/`, `Intermediate/`, `Saved/`, `DerivedDataCache/`, `Build/` | Recreated by the first editor launch. This machine had a 125 MB asset-registry cache and a 380 MB precompiled header in `Intermediate/`. Both are over GitHub's 100 MB file limit. |
| `logs/`, `scripts/__pycache__/`, `*.bak` | Local output. |

Git LFS is declared in `.gitattributes` for `.uasset`, `.umap`, textures, audio, archives, and `.mp4`, but `git-lfs` is not installed on the machine that wrote this file. No Unreal assets are waiting to be uploaded. Install Git LFS before adding a file of those types that could approach 100 MB. Do not rewrite the existing video into an LFS pointer.

## Bring the new machine up

1. Install Unreal Engine 5.8.4 so this file exists and is executable:

   `/home/user/UnrealEngine/UE_5.8.4/Engine/Binaries/Linux/UnrealEditor`

   If the engine lives somewhere else, change `ENGINE` in `scripts/launch-editor.sh`. The script pins Unreal off CPUs 0–1, sets idle I/O priority, and caps it at 16 GB soft / 24 GB hard. Without `nvidia-smi` it adds software rendering. The picture preset in the README matches this machine's RTX 5060 Ti and a 1024×768 desktop. Another GPU can still open the project.

2. Clone and enter the repo. Python 3.10 is enough. The third-party package the tests import is NumPy. This machine used Python 3.10.12 and NumPy 1.21.5. Gym, Gymnasium, and Stable-Baselines are not installed and are not required. The routing environment is `mmg_env.make_routing_env` (`MaritimeRouting-v0`).

3. Run the Python checks from `scripts/` before opening the editor:

   ```bash
   cd scripts
   python3 -m unittest -v
   python3 pretrain_validate.py
   ```

   `unittest` with no arguments discovers `test_*.py` in that directory. The training gate runs `test_turning_circle` and `test_fuel_units` and must print `TRAINING_GATE pass`. There is no trainer and no checkpoint.

4. Create `.env` in the repo root when this machine should push:

   ```bash
   GITHUB_TOKEN=the-token-from-the-previous-machine
   ```

   Do not commit that file. `git status` should keep showing it ignored.

5. The first editor launch compiles the C++ module and fills `Binaries/` and `Intermediate/`. That is expected.

   Headless buoyancy check, about 12 seconds, log `logs/ue_water_test.log`:

   ```bash
   scripts/run-water-test.sh
   ```

   A good run prints `WATER TEST PASS`. That line checks the wave query, the two cubes, and the kinematic hull. It does not judge the rendered picture.

   Windowed fleet demo, log `logs/fleet_demo.log`:

   ```bash
   scripts/run-fleet-demo.sh
   ```

## How the live fleet fits together

`AFleetEnvironment::LaunchPhysics` starts `scripts/mmg_physics.py` unless something is already bound to `127.0.0.1:9001`. The fleet sends the environment on that UDP port and applies the returned surge and sway. Port `9000` belongs to the separate water-test ship in `ShipPawn`. The fleet does not use 9000.

F5, F6, and F7 change only the visual sea (calm, moderate, rough). They do not change the wave height sent to Python. `[` and `]` change the visual period. F8, F10, and F12 select clear, cloudy, and rain. T and G step the hour. N toggles the day-night cycle. F5 used to open the engine shader-complexity view; `Config/DefaultInput.ini` removes that binding so the fleet control receives the key.

The three hulls are a 300 m container ship, a 245 m Aframax tanker, and a 225 m Panamax bulker. Dimensions and the checked force-model limits are in `docs/task3_visualization_and_physics.md`. The visual mesh, wake, and what was actually seen are in `docs/ocean_visuals.md`.

## Contracts the next change has to keep

`docs/MODEL_INTEGRATION_CONTRACT.md` is version 3. Observation length 12 and action length 2 are unchanged. Action value 0 on the speed axis is half service speed. The reward has an initial fuel term. `fuel_reward_per_kg=0` recovers the version 2 reward.

`docs/TELEMETRY_SCHEMA.md` is schema version 1 (`maritime_route_telemetry`). It reads ship state. It does not integrate motion and does not change the observation or the action.

`scripts/sac_agent.py` is a local NumPy smoke test with a 256-step unattended cap. It is not the network to replace. `scripts/inference_adapter.py` is the boundary for a policy that is still pending a checkpoint, framework, and dtype. The Unreal autopilot still owns the UDP socket.

`scripts/encounter.py` is a near-term encounter check. It is not full COLREG. `scripts/navigable_water.py` has no coastline or bathymetry survey. An empty chart is unknown water, not safe water.

## Push from the new machine

`scripts/auto-commit.sh` stages the work tree, drops `.env` and any non-LFS file over 90 MB, commits, and pushes `main` with the token. It does not use `--force`.

To push by hand, use the same token as a GitHub username `x-access-token` and do not put the token in the remote URL that gets saved. Then:

```bash
git status -sb
git fetch origin main
git push origin HEAD:main
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git status -sb
```

The two hashes match, and `git status -sb` shows `main...origin/main` with no ahead or behind count, when the push landed.
