import math
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import mmg_env
import mmg_physics as mmg
import route_telemetry as telemetry


def sea(current_ms, current_deg):
    return {
        "wind_ms": 0.0, "wind_deg": 0.0,
        "current_ms": current_ms, "current_deg": current_deg,
        "wave_m": 0.0, "wave_deg": 0.0,
    }


class SpeedTest(unittest.TestCase):
    def test_current_with_against_and_across_the_bow(self):
        with_current = telemetry.kinematic_speeds(0.0, 500.0, 0.0, 100.0, 0.0)
        self.assertAlmostEqual(with_current["sog_m_s"], 5.0, places=6)
        self.assertAlmostEqual(with_current["stw_m_s"], 4.0, places=6)
        self.assertAlmostEqual(with_current["cog_deg"], 0.0, places=6)
        self.assertAlmostEqual(with_current["heading_deg"], 0.0, places=6)

        against = telemetry.kinematic_speeds(0.0, 500.0, 0.0, 100.0, 180.0)
        self.assertAlmostEqual(against["sog_m_s"], 5.0, places=6)
        self.assertAlmostEqual(against["stw_m_s"], 6.0, places=6)

        across = telemetry.kinematic_speeds(0.0, 500.0, 0.0, 100.0, 90.0)
        self.assertAlmostEqual(across["sog_m_s"], 5.0, places=6)
        self.assertAlmostEqual(across["stw_m_s"], math.hypot(5.0, 1.0), places=6)
        self.assertNotAlmostEqual(across["stw_m_s"], across["sog_m_s"] + 1.0, places=3)
        self.assertAlmostEqual(across["ground_east_m_s"], across["water_east_m_s"] + across["current_east_m_s"], places=6)
        self.assertAlmostEqual(across["ground_north_m_s"], across["water_north_m_s"] + across["current_north_m_s"], places=6)

    def test_heading_changes_the_ground_direction_and_not_the_speed_magnitude(self):
        east = telemetry.kinematic_speeds(0.0, 400.0, 0.0, 0.0, 0.0)
        north = telemetry.kinematic_speeds(90.0, 400.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(east["sog_m_s"], north["sog_m_s"], places=6)
        self.assertAlmostEqual(east["stw_m_s"], east["sog_m_s"], places=6)
        self.assertAlmostEqual(north["cog_deg"], 90.0, places=6)
        self.assertAlmostEqual(north["ground_north_m_s"], 4.0, places=6)
        self.assertAlmostEqual(north["ground_east_m_s"], 0.0, places=6)

    def test_sway_makes_cog_differ_from_heading(self):
        speeds = telemetry.kinematic_speeds(0.0, 0.0, 200.0, 0.0, 0.0)
        self.assertAlmostEqual(speeds["heading_deg"], 0.0, places=6)
        self.assertAlmostEqual(speeds["cog_deg"], 90.0, places=6)
        self.assertNotAlmostEqual(speeds["heading_deg"], speeds["cog_deg"], places=3)

    def test_zero_current_and_near_zero_ground_speed(self):
        still = telemetry.kinematic_speeds(10.0, 0.0, 0.0, 0.0, 40.0)
        self.assertAlmostEqual(still["sog_m_s"], 0.0, places=6)
        self.assertAlmostEqual(still["stw_m_s"], 0.0, places=6)
        self.assertIsNone(still["cog_deg"])
        self.assertAlmostEqual(still["heading_deg"], 10.0, places=6)
        wrapped = telemetry.kinematic_speeds(190.0, 300.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(wrapped["heading_deg"], -170.0, places=6)
        self.assertAlmostEqual(wrapped["cog_deg"], -170.0, places=6)

    def test_missing_invalid_and_stale_inputs_stay_null(self):
        missing = telemetry.kinematic_speeds(0.0, 500.0, 0.0, None, None)
        self.assertAlmostEqual(missing["sog_m_s"], 5.0, places=6)
        self.assertIsNone(missing["stw_m_s"])
        self.assertEqual(missing["sample_quality"], "partial")
        invalid = telemetry.kinematic_speeds(0.0, float("nan"), 0.0, 10.0, 0.0)
        self.assertIsNone(invalid["sog_m_s"])
        self.assertIsNone(invalid["stw_m_s"])
        self.assertEqual(invalid["sample_quality"], "invalid")
        bad_current = telemetry.kinematic_speeds(0.0, 500.0, 0.0, float("inf"), 0.0)
        self.assertAlmostEqual(bad_current["sog_m_s"], 5.0, places=6)
        self.assertIsNone(bad_current["stw_m_s"])
        stale = telemetry.kinematic_speeds(0.0, 500.0, 0.0, 100.0, 0.0, stale=True)
        self.assertIsNone(stale["sog_m_s"])
        self.assertIsNone(stale["stw_m_s"])
        self.assertIsNone(stale["cog_deg"])
        self.assertEqual(stale["sample_quality"], "stale")

    def test_position_uses_ground_velocity_and_current_is_subtracted_once(self):
        # Expected values are written out here, not copied from the function.
        surge_cms, sway_cms = 400.0, 100.0
        current_east, current_north = 0.0, 0.5
        ground_east, ground_north = surge_cms / 100.0, sway_cms / 100.0
        water_east = ground_east - current_east
        water_north = ground_north - current_north
        speeds = telemetry.kinematic_speeds(0.0, surge_cms, sway_cms, 50.0, 90.0)
        self.assertAlmostEqual(speeds["sog_m_s"], math.hypot(ground_east, ground_north), places=6)
        self.assertAlmostEqual(speeds["stw_m_s"], math.hypot(water_east, water_north), places=6)
        self.assertAlmostEqual(speeds["cog_deg"], math.degrees(math.atan2(ground_north, ground_east)), places=6)
        self.assertNotAlmostEqual(speeds["heading_deg"], speeds["cog_deg"], places=3)
        ship = list(mmg_env.reference_ship(surge_cms=surge_cms))
        ship[2] = sway_cms
        moved = mmg_env.advance_position(tuple(ship), 1.0)
        self.assertAlmostEqual(moved[16] / 100.0, ground_east, places=6)
        self.assertAlmostEqual(moved[17] / 100.0, ground_north, places=6)
        self.assertNotAlmostEqual(moved[17] / 100.0, ground_north + current_north, places=3)
        twice = math.hypot(ground_east - 2.0 * current_east, ground_north - 2.0 * current_north)
        self.assertNotAlmostEqual(speeds["stw_m_s"], twice, places=3)

    def test_hand_calculated_current_from_both_sides(self):
        # current_deg is the direction the water moves toward, 0 along +X.
        # At heading 0, +Y is the code's right vector. These two cases are the
        # two beam directions. Expected numbers are written here, not copied
        # from kinematic_speeds.
        knot = 1.0 / mmg.KNOT_MS
        calm = telemetry.kinematic_speeds(0.0, 500.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(calm["sog_m_s"], 5.0, places=6)
        self.assertAlmostEqual(calm["stw_m_s"], 5.0, places=6)
        self.assertAlmostEqual(calm["cog_deg"], 0.0, places=6)
        toward_positive_y = telemetry.kinematic_speeds(0.0, 500.0, 0.0, 100.0, 90.0)
        self.assertAlmostEqual(toward_positive_y["ground_east_m_s"], 5.0, places=6)
        self.assertAlmostEqual(toward_positive_y["ground_north_m_s"], 0.0, places=6)
        self.assertAlmostEqual(toward_positive_y["water_east_m_s"], 5.0, places=6)
        self.assertAlmostEqual(toward_positive_y["water_north_m_s"], -1.0, places=6)
        self.assertAlmostEqual(toward_positive_y["sog_m_s"], 5.0, places=6)
        self.assertAlmostEqual(toward_positive_y["stw_m_s"], math.hypot(5.0, 1.0), places=6)
        toward_negative_y = telemetry.kinematic_speeds(0.0, 500.0, 0.0, 100.0, -90.0)
        self.assertAlmostEqual(toward_negative_y["water_north_m_s"], 1.0, places=6)
        self.assertAlmostEqual(toward_negative_y["stw_m_s"], math.hypot(5.0, 1.0), places=6)
        self.assertAlmostEqual(toward_positive_y["sog_m_s"] * knot, 5.0 * knot, places=4)
        wrapped = telemetry.kinematic_speeds(-190.0, 400.0, 0.0, 0.0, 0.0)
        self.assertAlmostEqual(wrapped["heading_deg"], 170.0, places=6)
        self.assertAlmostEqual(wrapped["cog_deg"], 170.0, places=6)


class FuelTelemetryTest(unittest.TestCase):
    def test_reference_rates_and_the_shaft_identity(self):
        for power_kw, hour_kg in ((100.0, 17.5), (1000.0, 175.0)):
            rate = mmg.fuel_rate_kg_s(power_kw)
            self.assertAlmostEqual(rate * 3600.0, hour_kg, places=6)
            tonnes_per_hour = rate * 3.6
            recovered = telemetry.fuel_from_tonnes_per_hour(tonnes_per_hour)
            self.assertEqual(recovered["fuel_status"], "estimated")
            self.assertEqual(recovered["power_kw"] is not None, True)
            self.assertAlmostEqual(recovered["power_kw"], power_kw, places=6)
            self.assertAlmostEqual(recovered["fuel_rate_kg_s"], rate, places=9)
            self.assertAlmostEqual(recovered["fuel_rate_kg_h"], hour_kg, places=6)
        self.assertAlmostEqual(mmg.fuel_rate_kg_s(1000.0), 0.0486111111, places=7)
        self.assertAlmostEqual(mmg.fuel_rate_kg_s(100.0), 0.0048611111, places=7)

    def test_invalid_power_does_not_become_fuel(self):
        for bad in (None, float("nan"), -1.0, float("inf")):
            result = telemetry.fuel_from_tonnes_per_hour(bad)
            self.assertIsNone(result["fuel_rate_kg_s"])
            self.assertIsNone(result["power_kw"])
            self.assertIn(result["fuel_status"], ("unavailable", "invalid"))

    def test_variable_steps_accumulate_once_and_a_retry_does_not(self):
        root = tempfile.mkdtemp(prefix="telemetry_")
        try:
            log = telemetry.RouteTelemetry(root, "run-a", "route-a")
            first = log.record_sample({
                "step_index": 1, "sim_time_s": 0.5, "control_step_s": 0.5,
                "fuel_status": "estimated", "fuel_step_kg": 0.2, "fuel_rate_kg_s": 0.4,
                "distance_step_m": 3.0, "route_status": "running", "sog_m_s": 6.0,
            })
            second = log.record_sample({
                "step_index": 2, "sim_time_s": 2.5, "control_step_s": 2.0,
                "fuel_status": "estimated", "fuel_step_kg": 0.05, "fuel_rate_kg_s": 0.025,
                "distance_step_m": 8.0, "route_status": "running", "sog_m_s": 4.0,
            })
            retry = log.record_sample({
                "step_index": 2, "fuel_status": "estimated", "fuel_step_kg": 0.05, "distance_step_m": 8.0,
            })
            self.assertEqual(first, "recorded")
            self.assertEqual(second, "recorded")
            self.assertEqual(retry, "duplicate")
            self.assertAlmostEqual(log.fuel_cumulative_kg, 0.25, places=9)
            self.assertAlmostEqual(log.distance_travelled_m, 11.0, places=9)
            body = log.finalize("truncated")
            rows = telemetry.read_jsonl(log.json_path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(len(telemetry.read_csv(log.csv_path)), 2)
            self.assertAlmostEqual(body["elapsed_s"], 2.0, places=6)
            self.assertAlmostEqual(body["stats"]["sog_m_s"]["min"], 4.0, places=6)
            self.assertAlmostEqual(body["stats"]["sog_m_s"]["max"], 6.0, places=6)
            self.assertEqual(body["waypoints_missed"], 1)
        finally:
            shutil.rmtree(root)

    def test_env_step_matches_authoritative_state_without_a_second_integral(self):
        root = tempfile.mkdtemp(prefix="telemetry_env_")
        try:
            env = mmg_env.MaritimeRoutingEnv(destination_m=(400.0, 0.0), step_s=1.0, max_steps=4, sea=sea(0.5, 0.0))
            env.reset(options={"heading_deg": 0.0})
            log = telemetry.RouteTelemetry(root, "env-run", "straight")
            fuel = 0.0
            distance = 0.0
            for _ in range(2):
                _, _, terminated, truncated, info = env.step((0.0, 1.0))
                fuel += info["fuel_t"] * 1000.0
                distance += info["route_m"]
                status = log.record_env(env, info, info["termination"], info["route_m"], info["fuel_t"])
                self.assertEqual(status, "recorded")
                self.assertFalse(terminated)
                self.assertFalse(truncated)
            self.assertEqual(log.record_env(env, info, info["termination"], info["route_m"], info["fuel_t"]), "duplicate")
            self.assertAlmostEqual(log.fuel_cumulative_kg, fuel, places=9)
            self.assertAlmostEqual(log.distance_travelled_m, distance, places=9)
            rows = telemetry.read_jsonl(log.json_path)
            self.assertAlmostEqual(rows[-1]["sog_m_s"], math.hypot(env.ship[1], env.ship[2]) / 100.0, places=6)
            self.assertAlmostEqual(rows[-1]["x_m"], info["x_m"], places=6)
            self.assertAlmostEqual(rows[-1]["rudder_deg"], info["rudder_deg"], places=6)
            self.assertAlmostEqual(rows[-1]["distance_remaining_m"], info["distance_m"], places=6)
            self.assertEqual(rows[-1]["inner_step_s"], 0.02)
            self.assertIsNone(rows[-1]["latitude_deg"])
            self.assertIsNone(rows[-1]["rpm"])
            self.assertEqual(rows[-1]["power_type"], "shaft")
            self.assertEqual(rows[-1]["fuel_status"], "estimated")
            self.assertGreater(rows[-1]["sog_m_s"], 0.0)
            self.assertNotAlmostEqual(rows[-1]["stw_m_s"], rows[-1]["sog_m_s"], places=3)
            held = env.ship
            log.record_env(env, info, info["termination"], 0.0, 0.0)
            self.assertEqual(env.ship, held)
            summary = log.finalize()
            self.assertEqual(summary["run_id"], "env-run")
            self.assertEqual(summary["export_status"], "complete")
            self.assertTrue(os.path.exists(log.summary_path))
        finally:
            shutil.rmtree(root)


class ExportTest(unittest.TestCase):
    def test_schema_nulls_unique_names_and_a_failed_directory(self):
        root = tempfile.mkdtemp(prefix="telemetry_export_")
        try:
            first = telemetry.RouteTelemetry(root, "same", "leg")
            first.record_sample({
                "step_index": 1, "sim_time_s": 1.0, "route_status": "running",
                "fuel_status": "unavailable", "sog_m_s": None, "data_source": "synthetic_fixture",
                "warning": "synthetic fixture, not a voyage",
            })
            with open(first.status_path, encoding="utf-8") as handle:
                open_status = handle.read().strip()
            self.assertEqual(open_status, "partial")
            body = first.finalize("interrupted")
            self.assertEqual(body["export_status"], "partial")
            csv_rows = telemetry.read_csv(first.csv_path)
            json_rows = telemetry.read_jsonl(first.json_path)
            self.assertEqual(csv_rows[0]["run_id"], "same")
            self.assertEqual(csv_rows[0]["schema_version"], "1")
            self.assertEqual(csv_rows[0]["latitude_deg"], "")
            self.assertIsNone(json_rows[0]["latitude_deg"])
            self.assertIsNone(json_rows[0]["sog_m_s"])
            self.assertEqual(json_rows[0]["data_source"], "synthetic_fixture")
            self.assertEqual(set(json_rows[0]), set(telemetry.FIELDS))
            second = telemetry.RouteTelemetry(root, "same", "leg")
            self.assertNotEqual(first.csv_path, second.csv_path)
            self.assertTrue(os.path.exists(first.csv_path))
            second.finalize("completed")
            blocked = os.path.join(root, "not_a_directory")
            with open(blocked, "w", encoding="utf-8") as handle:
                handle.write("x")
            failed = telemetry.RouteTelemetry(blocked, "run", "route")
            self.assertEqual(failed.record_sample({"step_index": 1, "fuel_status": "estimated", "fuel_step_kg": 1.0}), "export_failed")
            self.assertEqual(failed.fuel_cumulative_kg, 0.0)
            self.assertTrue(failed.export_error)
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
