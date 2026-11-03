"""Route telemetry. Reads ship state. Does not integrate motion or fuel.

Speeds use the same ground vector as `advance_position` and `step_once`:
body surge and sway, rotated by heading, in centimetres per second.
Current comes from `mmg_physics.direction`. Water-relative velocity is that
ground vector minus the current vector. STW, SOG, and COG are derived from
those two vectors. Scalar current speed is never added to STW.

Fuel rate is the tonnes-per-hour value `integrate` already returned.
`fuel_tph = fuel_rate_kg_s(shaft_kW) * 3.6`, so kilograms per second are
`fuel_tph / 3.6`. Shaft kilowatts are that rate inverted through the same
175 g/kWh constant. This is an estimate, not a measured shaft meter.
Cumulative kilograms add the environment's one-step integral (`fuel_t`,
tonnes) once per step index. They do not walk the 0.02 s substeps again.

There is no geodetic origin in this project. Latitude and longitude stay
null. RPM and throttle are not in the ship tuple and stay null.
"""

import csv
import json
import math
import os
import uuid
from datetime import datetime, timezone

import mmg_physics as mmg

SCHEMA_VERSION = 1
SCHEMA_NAME = "maritime_route_telemetry"
# Below this ground speed, COG is not a direction.
COG_MIN_M_S = 0.05
SFC_G_PER_KWH = mmg.SFOC_G_PER_KWH
MISSING_CSV = ""

FIELDS = (
    "schema_version",
    "data_source",
    "utc",
    "sim_time_s",
    "control_step_s",
    "inner_step_s",
    "run_id",
    "route_id",
    "vessel_id",
    "waypoint_id",
    "step_index",
    "route_status",
    "x_m",
    "y_m",
    "latitude_deg",
    "longitude_deg",
    "heading_deg",
    "cog_deg",
    "rudder_deg",
    "ordered_speed_m_s",
    "rpm",
    "throttle",
    "stw_m_s",
    "sog_m_s",
    "ground_east_m_s",
    "ground_north_m_s",
    "water_east_m_s",
    "water_north_m_s",
    "current_east_m_s",
    "current_north_m_s",
    "current_m_s",
    "current_deg",
    "wind_m_s",
    "wind_deg",
    "wave_m",
    "wave_deg",
    "distance_remaining_m",
    "cross_track_m",
    "heading_error_rad",
    "arrived",
    "power_kw",
    "power_type",
    "power_status",
    "fuel_rate_kg_s",
    "fuel_rate_kg_h",
    "fuel_step_kg",
    "fuel_cumulative_kg",
    "sfc_g_per_kwh",
    "fuel_status",
    "sample_quality",
    "warning",
)


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def _blank():
    row = {name: None for name in FIELDS}
    row["schema_version"] = SCHEMA_VERSION
    row["sfc_g_per_kwh"] = SFC_G_PER_KWH
    row["power_type"] = "shaft"
    row["latitude_deg"] = None
    row["longitude_deg"] = None
    row["rpm"] = None
    row["throttle"] = None
    return row


def kinematic_speeds(heading_deg, surge_cms, sway_cms, current_cms=None, current_deg=None, stale=False):
    """Return STW, SOG, and COG. Missing results are None, never zero substitutes."""
    speeds = {
        "heading_deg": None,
        "stw_m_s": None,
        "sog_m_s": None,
        "cog_deg": None,
        "ground_east_m_s": None,
        "ground_north_m_s": None,
        "water_east_m_s": None,
        "water_north_m_s": None,
        "current_east_m_s": None,
        "current_north_m_s": None,
        "current_m_s": None,
        "current_deg": None,
        "sample_quality": "ok",
        "warning": None,
    }
    if stale:
        speeds["sample_quality"] = "stale"
        speeds["warning"] = "stale velocity or current; speeds left unset"
        return speeds
    if not (_finite(heading_deg) and _finite(surge_cms) and _finite(sway_cms)):
        speeds["sample_quality"] = "invalid"
        speeds["warning"] = "heading or body velocity is missing or non-finite"
        return speeds
    yaw = math.radians(heading_deg)
    forward = (math.cos(yaw), math.sin(yaw))
    right = (-math.sin(yaw), math.cos(yaw))
    ground_x = forward[0] * surge_cms + right[0] * sway_cms
    ground_y = forward[1] * surge_cms + right[1] * sway_cms
    speeds["heading_deg"] = mmg.wrap_deg(heading_deg)
    speeds["ground_east_m_s"] = ground_x / 100.0
    speeds["ground_north_m_s"] = ground_y / 100.0
    sog = math.hypot(ground_x, ground_y) / 100.0
    speeds["sog_m_s"] = sog
    warnings = []
    if sog >= COG_MIN_M_S:
        speeds["cog_deg"] = mmg.wrap_deg(math.degrees(math.atan2(ground_y, ground_x)))
    else:
        warnings.append("ground velocity near zero; COG unset")
    current_missing = current_cms is None and current_deg is None
    if current_missing:
        speeds["sample_quality"] = "partial"
        warnings.append("current unavailable; STW unset")
        speeds["warning"] = "; ".join(warnings)
        return speeds
    if not (_finite(current_cms) and _finite(current_deg)):
        speeds["sample_quality"] = "invalid"
        warnings.append("current is non-finite; STW unset")
        speeds["warning"] = "; ".join(warnings)
        return speeds
    current = mmg.direction(current_deg, current_cms)
    water_x = ground_x - current[0]
    water_y = ground_y - current[1]
    speeds["current_east_m_s"] = current[0] / 100.0
    speeds["current_north_m_s"] = current[1] / 100.0
    speeds["current_m_s"] = math.hypot(current[0], current[1]) / 100.0
    speeds["current_deg"] = mmg.wrap_deg(current_deg)
    speeds["water_east_m_s"] = water_x / 100.0
    speeds["water_north_m_s"] = water_y / 100.0
    speeds["stw_m_s"] = math.hypot(water_x, water_y) / 100.0
    speeds["warning"] = "; ".join(warnings) if warnings else None
    return speeds


def fuel_from_tonnes_per_hour(fuel_tph):
    """Invert the published tonnes-per-hour identity. Do not accept a bad rate."""
    if fuel_tph is None:
        return {"power_kw": None, "fuel_rate_kg_s": None, "fuel_rate_kg_h": None, "fuel_status": "unavailable", "warning": "fuel rate unavailable"}
    if not _finite(fuel_tph) or fuel_tph < 0.0:
        return {"power_kw": None, "fuel_rate_kg_s": None, "fuel_rate_kg_h": None, "fuel_status": "invalid", "warning": "fuel rate is negative or non-finite"}
    kg_s = fuel_tph / 3.6
    return {
        "power_kw": kg_s * 3_600_000.0 / SFC_G_PER_KWH,
        "fuel_rate_kg_s": kg_s,
        "fuel_rate_kg_h": kg_s * 3600.0,
        "fuel_status": "estimated",
        "warning": None,
    }


def _route_status(termination):
    if termination in (None, "running"):
        return "running"
    if termination == "arrived":
        return "completed"
    if termination in ("failure", "collision", "land", "shallow", "chart_invalid", "chart_unknown"):
        return "failed"
    if termination == "truncated":
        return "truncated"
    return "interrupted"


def _num(value):
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


class RouteTelemetry:
    """Append-only samples and running totals. Sample bodies are not kept in memory."""

    def __init__(self, directory, run_id, route_id, vessel_id="reference-hull", waypoint_id="destination", overwrite=False):
        self.directory = directory
        self.run_id = str(run_id)
        self.route_id = str(route_id)
        self.vessel_id = str(vessel_id)
        self.waypoint_id = str(waypoint_id)
        self.overwrite = bool(overwrite)
        self.export_error = None
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            self.export_error = "directory failed: %s" % exc
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        token = uuid.uuid4().hex[:8]
        stem = "%s_%s_%s_%s" % (self._safe(self.run_id), self._safe(self.route_id), stamp, token)
        self.stem = self._unused_stem(stem)
        self.csv_path = os.path.join(directory, self.stem + ".csv")
        self.json_path = os.path.join(directory, self.stem + ".jsonl")
        self.summary_path = os.path.join(directory, self.stem + ".summary.json")
        self.status_path = os.path.join(directory, self.stem + ".status.txt")
        self._last_step = None
        self.fuel_cumulative_kg = 0.0
        self.distance_travelled_m = 0.0
        self.sample_count = 0
        self.fuel_sample_count = 0
        self.warnings = []
        self.sim_start_s = None
        self.sim_end_s = None
        self.route_status = "initializing"
        self.finalized = False
        self._stats = {}
        self._csv = None
        self._json = None
        self._open_writers()
        self._write_status("partial")

    @staticmethod
    def _safe(text):
        cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text)
        return cleaned[:40] or "run"

    def _unused_stem(self, stem):
        if self.overwrite:
            return stem
        candidate = stem
        suffix = 2
        while os.path.exists(os.path.join(self.directory, candidate + ".csv")) or os.path.exists(os.path.join(self.directory, candidate + ".jsonl")):
            candidate = "%s_%d" % (stem, suffix)
            suffix += 1
        return candidate

    def _open_writers(self):
        try:
            self._csv = open(self.csv_path, "w", newline="", encoding="utf-8")
            writer = csv.DictWriter(self._csv, fieldnames=FIELDS, extrasaction="ignore", restval="")
            writer.writeheader()
            self._writer = writer
            self._json = open(self.json_path, "w", encoding="utf-8")
        except OSError as exc:
            self.export_error = "open failed: %s" % exc
            if self._csv is not None:
                self._csv.close()
            self._csv = None
            self._json = None
            self._writer = None

    def _write_status(self, text):
        try:
            with open(self.status_path, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as exc:
            self.export_error = "status write failed: %s" % exc

    def _remember(self, name, value):
        if not _finite(value):
            return
        count, total, low, high = self._stats.get(name, (0, 0.0, value, value))
        self._stats[name] = (count + 1, total + value, min(low, value), max(high, value))

    def record_sample(self, sample):
        """Append one sample. A repeated step index is ignored and does not add fuel."""
        if self.finalized:
            return "closed"
        step = sample.get("step_index")
        if step is not None and self._last_step is not None and step <= self._last_step:
            return "duplicate"
        if self.export_error and self._csv is None:
            return "export_failed"
        row = _blank()
        row.update(sample)
        row["schema_version"] = SCHEMA_VERSION
        row["run_id"] = self.run_id
        row["route_id"] = self.route_id
        row["vessel_id"] = self.vessel_id
        row["waypoint_id"] = sample.get("waypoint_id") or self.waypoint_id
        row["utc"] = sample.get("utc") or utc_now()
        next_fuel = self.fuel_cumulative_kg
        next_fuel_samples = self.fuel_sample_count
        increment = sample.get("fuel_step_kg")
        if sample.get("fuel_status") == "estimated" and _finite(increment) and increment >= 0.0:
            next_fuel += increment
            next_fuel_samples += 1
        row["fuel_cumulative_kg"] = next_fuel
        next_distance = self.distance_travelled_m
        distance = sample.get("distance_step_m")
        if _finite(distance) and distance >= 0.0:
            next_distance += distance
        try:
            self._writer.writerow({key: _num(row.get(key)) for key in FIELDS})
            self._csv.flush()
            payload = {key: row.get(key) for key in FIELDS}
            self._json.write(json.dumps(payload, allow_nan=False) + "\n")
            self._json.flush()
        except (OSError, ValueError, TypeError) as exc:
            self.export_error = "sample write failed: %s" % exc
            return "export_failed"
        self.fuel_cumulative_kg = next_fuel
        self.fuel_sample_count = next_fuel_samples
        self.distance_travelled_m = next_distance
        if _finite(sample.get("sim_time_s")):
            if self.sim_start_s is None:
                self.sim_start_s = sample["sim_time_s"]
            self.sim_end_s = sample["sim_time_s"]
        if sample.get("route_status"):
            self.route_status = sample["route_status"]
        if sample.get("warning"):
            self.warnings.append(sample["warning"])
        for name in ("sog_m_s", "stw_m_s", "fuel_rate_kg_s", "power_kw", "cross_track_m"):
            self._remember(name, row.get(name))
        self._last_step = step
        self.sample_count += 1
        return "recorded"

    def record_env(self, env, info, termination, distance_step_m=0.0, fuel_step_t=0.0, stale=False):
        """Read one environment step. `fuel_step_t` is the step's own tonne integral."""
        speeds = kinematic_speeds(
            env.ship[0], env.ship[1], env.ship[2],
            env.clock.get("current_cms"), env.clock.get("current_deg"),
            stale=stale,
        )
        fuel = fuel_from_tonnes_per_hour(None if stale else info.get("fuel_tph"))
        if stale:
            fuel = {"power_kw": None, "fuel_rate_kg_s": None, "fuel_rate_kg_h": None, "fuel_status": "unavailable", "warning": "stale step; fuel left unset"}
        warning = "; ".join(item for item in (speeds["warning"], fuel["warning"], info.get("warning")) if item)
        sample = {
            "data_source": "synthetic_fixture" if info.get("data_source") == "synthetic_fixture" else "mmg_env",
            "sim_time_s": env.clock.get("time"),
            "control_step_s": env.step_s,
            "inner_step_s": info.get("inner_dt_s", mmg_inner()),
            "step_index": env.steps,
            "route_status": _route_status(termination),
            "x_m": None if stale else env.ship[16] / 100.0,
            "y_m": None if stale else env.ship[17] / 100.0,
            "rudder_deg": None if stale else env.ship[4],
            "ordered_speed_m_s": None if stale else env.ship[5],
            "wind_m_s": env.clock.get("wind_cms", 0.0) / 100.0 if _finite(env.clock.get("wind_cms")) else None,
            "wind_deg": env.clock.get("wind_deg"),
            "wave_m": env.clock.get("wave_cm", 0.0) / 100.0 if _finite(env.clock.get("wave_cm")) else None,
            "wave_deg": env.clock.get("wave_deg"),
            "distance_remaining_m": None if stale else info.get("distance_m"),
            "cross_track_m": None if stale else info.get("cross_track_m"),
            "heading_error_rad": None if stale else info.get("heading_error_rad"),
            "arrived": bool(info.get("arrived")) if not stale else None,
            "power_kw": fuel["power_kw"],
            "power_status": "estimated" if fuel["fuel_status"] == "estimated" else fuel["fuel_status"],
            "fuel_rate_kg_s": fuel["fuel_rate_kg_s"],
            "fuel_rate_kg_h": fuel["fuel_rate_kg_h"],
            "fuel_step_kg": None if fuel["fuel_status"] != "estimated" or not _finite(fuel_step_t) or fuel_step_t < 0.0 else fuel_step_t * 1000.0,
            "fuel_status": fuel["fuel_status"],
            "sample_quality": speeds["sample_quality"],
            "warning": warning or None,
            "distance_step_m": 0.0 if stale or not _finite(distance_step_m) or distance_step_m < 0.0 else distance_step_m,
        }
        sample.update({key: speeds[key] for key in (
            "heading_deg", "cog_deg", "stw_m_s", "sog_m_s",
            "ground_east_m_s", "ground_north_m_s", "water_east_m_s", "water_north_m_s",
            "current_east_m_s", "current_north_m_s", "current_m_s", "current_deg",
        )})
        return self.record_sample(sample)

    def summary(self, export_status):
        def stat(name):
            if name not in self._stats:
                return {"count": 0, "mean": None, "min": None, "max": None}
            count, total, low, high = self._stats[name]
            return {"count": count, "mean": total / count, "min": low, "max": high}

        elapsed = None
        if self.sim_start_s is not None and self.sim_end_s is not None:
            elapsed = self.sim_end_s - self.sim_start_s
        coverage = None if self.sample_count == 0 else self.fuel_sample_count / self.sample_count
        return {
            "schema_version": SCHEMA_VERSION,
            "schema_name": SCHEMA_NAME,
            "data_source": "mmg_env",
            "units": {
                "position": "metres in the simulation X/Y frame, +X east and +Y north of that frame. Not geographic.",
                "speed": "metres per second",
                "angle": "degrees, 0 along +X, positive toward +Y, wrapped to [-180, 180]",
                "power": "shaft kilowatts estimated by inverting the 175 g/kWh fuel identity",
                "fuel": "estimated kilograms, from the environment step integral counted once",
                "csv_missing": "empty field",
                "json_missing": "null",
            },
            "run_id": self.run_id,
            "route_id": self.route_id,
            "vessel_id": self.vessel_id,
            "waypoint_id": self.waypoint_id,
            "route_status": self.route_status,
            "export_status": export_status,
            "sim_start_s": self.sim_start_s,
            "sim_end_s": self.sim_end_s,
            "elapsed_s": elapsed,
            "sample_count": self.sample_count,
            "distance_travelled_m": self.distance_travelled_m,
            "waypoints_completed": 1 if self.route_status == "completed" else 0,
            "waypoints_missed": 1 if self.route_status in ("truncated", "failed", "interrupted") else 0,
            "fuel_cumulative_kg": self.fuel_cumulative_kg,
            "fuel_sample_coverage": coverage,
            "sfc_g_per_kwh": SFC_G_PER_KWH,
            "power_type": "shaft",
            "stats": {name: stat(name) for name in ("sog_m_s", "stw_m_s", "fuel_rate_kg_s", "power_kw", "cross_track_m")},
            "warnings": self.warnings,
            "export_error": self.export_error,
            "csv_path": self.csv_path,
            "jsonl_path": self.json_path,
            "unavailable": ["latitude_deg", "longitude_deg", "rpm", "throttle", "shore", "depth", "chart_obstacles"],
        }

    def finalize(self, status=None):
        if status:
            self.route_status = status
        export_status = "complete" if self.export_error is None else "failed"
        if self.route_status == "interrupted" and self.export_error is None:
            export_status = "partial"
        body = self.summary(export_status)
        try:
            if self._csv:
                self._csv.flush()
                self._csv.close()
                self._csv = None
            if self._json:
                self._json.flush()
                self._json.close()
                self._json = None
            with open(self.summary_path, "w", encoding="utf-8") as handle:
                json.dump(body, handle, indent=2, allow_nan=False)
                handle.write("\n")
        except OSError as exc:
            self.export_error = "finalize failed: %s" % exc
            export_status = "failed"
            body["export_status"] = export_status
            body["export_error"] = self.export_error
        self._write_status(export_status)
        self.finalized = True
        return body


def mmg_inner():
    return 0.02


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
