#!/usr/bin/env python3
"""Fail-closed checks that must pass before model training.

This repository has no Gym environment and no training script. The fleet UDP
server, the water test, and the fleet demo do not call this gate. Any future
Python training entry point under this repo must call `enforce_training_gate`
or this scan rejects it.
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
SKIP_NAMES = {
    "pretrain_validate.py",
    "test_turning_circle.py",
    "test_fuel_units.py",
}
TRAINING_MARKERS = ("gym.make", "gymnasium", "stable_baselines", "model.learn")


def training_entry_points():
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [name for name in dirnames if name not in {".git", "__pycache__", "Intermediate", "Binaries", "Saved"}]
        for name in filenames:
            if not name.endswith(".py") or name in SKIP_NAMES:
                continue
            path = os.path.join(dirpath, name)
            if name.startswith("train") or name.endswith("_train.py"):
                found.append(path)
                continue
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                text = handle.read()
            if any(marker in text for marker in TRAINING_MARKERS):
                found.append(path)
    return found


def _parse(pattern, text, label):
    match = re.search(pattern, text)
    if not match:
        raise RuntimeError("could not verify %s from test output" % label)
    return match


def enforce_training_gate():
    """Run the turning-circle and fuel tests. Raise SystemExit on any failure."""
    for path in training_entry_points():
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            text = handle.read()
        if "enforce_training_gate" not in text:
            raise SystemExit("training entry point does not call the validation gate: %s" % path)

    command = [sys.executable, "-m", "unittest", "-v", "test_turning_circle", "test_fuel_units"]
    completed = subprocess.run(command, cwd=SCRIPTS, capture_output=True, text=True)
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    if completed.returncode != 0:
        sys.stderr.write(combined)
        raise SystemExit(completed.returncode or 1)

    turning = _parse(
        r"TURNING_CIRCLE steady_diameter_m=([0-9.]+) advance_m=([0-9.]+) tactical_diameter_m=([0-9.]+)",
        combined,
        "turning circle",
    )
    steady = float(turning.group(1))
    advance = float(turning.group(2))
    tactical = float(turning.group(3))
    if not (864.0 <= steady <= 1056.0 and 892.8 <= advance <= 1091.2):
        raise SystemExit("turning circle outside tolerance: steady %.1f m, advance %.1f m" % (steady, advance))
    if tactical <= 0.0:
        raise SystemExit("tactical diameter was not measured")

    fuel = _parse(r"FUEL_KG_S power_kw=1000 rate_kg_s=([0-9.]+) hour_kg=([0-9.]+)", combined, "fuel rate")
    rate = float(fuel.group(1))
    hour_kg = float(fuel.group(2))
    if abs(rate - 0.0486111111) > 1.0e-7 or abs(hour_kg - 175.0) > 1.0e-4:
        raise SystemExit("fuel rate failed verification: %.8f kg/s, %.3f kg/h" % (rate, hour_kg))
    if "REWARD_INVESTIGATION" not in combined:
        raise SystemExit("fuel reward investigation did not run")

    print("TRAINING_GATE pass steady_diameter_m=%.3f advance_m=%.3f tactical_diameter_m=%.3f fuel_kg_s=%.7f" % (steady, advance, tactical, rate))
    print("TRAINING_GATE entry_points=%d" % len(training_entry_points()))
    return 0


if __name__ == "__main__":
    try:
        enforce_training_gate()
    except RuntimeError as exc:
        sys.stderr.write("%s\n" % exc)
        raise SystemExit(2)
