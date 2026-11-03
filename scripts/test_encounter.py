"""Encounter decisions. Packet fixtures do not open the fleet socket."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import encounter
import fleet_state
import hull_separation
import mmg_env
import mmg_physics as mmg


def own(surge=450.0):
    return {
        "x_m": 0.0, "y_m": 0.0, "heading_deg": 0.0, "length_m": 300.0, "beam_m": 42.8,
        "surge_cms": surge, "sway_cms": 0.0,
    }


def vessel(**updates):
    body = {
        "x_m": 800.0, "y_m": 0.0, "heading_deg": 180.0, "length_m": 50.0, "beam_m": 16.0,
        "surge_cms": 450.0, "sway_cms": 0.0,
    }
    body.update(updates)
    return body


def flat_sea():
    return {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}


def deep_chart():
    return {"source": "synthetic_fixture", "land": [], "default_depth_m": 40.0}


class EncounterTest(unittest.TestCase):
    def test_collision_parallel_crossing_and_overtaking(self):
        self.assertFalse(encounter.COLREG_COVERAGE["full_compliance"])
        head_on = encounter.decide(own(), [vessel()], min_separation_m=100.0, horizon_s=120.0)
        self.assertEqual(head_on["kind"], "head_on")
        self.assertFalse(head_on["safe"])
        self.assertLess(head_on["override"][0], 0.0)

        parallel = encounter.decide(
            own(),
            [vessel(x_m=0.0, y_m=400.0, heading_deg=0.0, length_m=40.0)],
            min_separation_m=100.0, horizon_s=60.0,
        )
        self.assertEqual(parallel["kind"], "parallel")
        self.assertTrue(parallel["safe"])
        self.assertIsNone(parallel["override"])

        starboard = encounter.decide(
            own(),
            [vessel(x_m=500.0, y_m=-500.0, heading_deg=90.0, length_m=40.0)],
            min_separation_m=100.0, horizon_s=120.0,
        )
        self.assertEqual(starboard["kind"], "crossing")
        self.assertFalse(starboard["safe"])
        self.assertLess(starboard["override"][0], 0.0)

        port = encounter.decide(
            own(),
            [vessel(x_m=500.0, y_m=500.0, heading_deg=-90.0, length_m=40.0)],
            min_separation_m=100.0, horizon_s=120.0,
        )
        self.assertEqual(port["kind"], "crossing")
        self.assertEqual(port["override"][0], 0.0)
        self.assertEqual(port["override"][1], -1.0)

        overtaking = encounter.decide(
            own(),
            [vessel(x_m=350.0, y_m=0.0, heading_deg=0.0, surge_cms=150.0, length_m=40.0)],
            min_separation_m=50.0, horizon_s=180.0,
        )
        self.assertEqual(overtaking["kind"], "overtaking")
        self.assertFalse(overtaking["safe"])
        self.assertLess(overtaking["override"][0], 0.0)

    def test_bad_data_stops_and_a_course_change_reaches_the_helm(self):
        stale = encounter.decide(own(), [vessel(stale=True)], min_separation_m=100.0, horizon_s=60.0)
        self.assertEqual(stale["status"], "stale")
        self.assertIsNone(stale["safe"])
        self.assertEqual(stale["override"], (0.0, -1.0))
        missing = encounter.decide(own(), [vessel(surge_cms=float("nan"))])
        self.assertEqual(missing["status"], "invalid")
        self.assertIsNone(missing["safe"])
        self.assertEqual(encounter.decide(own(), [{"x_m": 10.0}])["status"], "invalid")

        other = vessel(x_m=300.0, y_m=220.0, heading_deg=0.0, length_m=40.0)
        env = mmg_env.MaritimeRoutingEnv(
            destination_m=(2000.0, 0.0), step_s=1.0, max_steps=5, sea=flat_sea(),
            traffic=[other], chart=deep_chart(), min_separation_m=80.0, encounter_horizon_s=180.0,
        )
        env.reset(options={"heading_deg": 0.0})
        _, _, terminated, _, first = env.step(np.array([0.0, 0.0]))
        self.assertFalse(first["helm_override"])
        self.assertTrue(first["traffic_safe"])
        self.assertFalse(terminated)
        half_speed = env.ship[15] / 100.0 * 0.5
        self.assertAlmostEqual(first["ordered_speed_ms"], half_speed, places=5)
        other["heading_deg"] = -90.0
        _, _, _, _, second = env.step(np.array([0.0, 0.0]))
        self.assertTrue(second["helm_override"])
        self.assertFalse(second["traffic_safe"])
        self.assertEqual(second["ordered_speed_ms"], 0.0)
        self.assertEqual(second["encounter"], "crossing")

    def test_parsed_packet_can_change_the_helm_without_a_live_socket(self):
        self.assertFalse(encounter.live_feed_status()["connected"])
        values = [0.0] * 18
        values[0] = 80000.0
        values[1] = 0.0
        values[2] = 180.0
        values[3] = 450.0
        values[9] = 5000.0
        values[10] = 1600.0
        header = mmg.HEADER.pack(mmg.REQ, 1, 1, 0.02, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        payload = header + mmg.SHIP.pack(4, *values)
        parsed = fleet_state.parse_mmg1(payload)
        traffic = fleet_state.traffic_from_parsed(parsed)
        self.assertEqual(traffic[0]["surge_cms"], 450.0)
        self.assertEqual(parsed["missing"], fleet_state.MISSING_FIELDS)
        env = mmg_env.MaritimeRoutingEnv(
            destination_m=(2000.0, 0.0), step_s=1.0, max_steps=3, sea=flat_sea(),
            traffic=traffic, chart=deep_chart(), min_separation_m=100.0, encounter_horizon_s=120.0,
        )
        env.reset(options={"heading_deg": 0.0})
        _, _, terminated, _, info = env.step(np.array([0.0, 1.0]))
        self.assertTrue(info["helm_override"])
        self.assertEqual(info["encounter"], "head_on")
        self.assertLess(info["rudder_deg"], 0.0)
        self.assertFalse(terminated)
        self.assertFalse(encounter.live_feed_status()["connected"])
        broken = bytearray(payload)
        nan = __import__("struct").pack("<f", float("nan"))
        surge_at = mmg.HEADER.size + 4 + 12
        broken[surge_at:surge_at + 4] = nan
        with self.assertRaises(fleet_state.IncompleteFleetState):
            fleet_state.parse_mmg1(bytes(broken))

    def test_overlap_hull_size_and_missing_data_change_the_decision(self):
        self.assertFalse(encounter.COLREG_COVERAGE["full_compliance"])
        overlapped = vessel(x_m=10.0, y_m=0.0, heading_deg=0.0, length_m=300.0, beam_m=40.0, surge_cms=0.0)
        self.assertLess(hull_separation.separation_m(own(), overlapped), 0.0)
        narrow = vessel(x_m=0.0, y_m=40.0, heading_deg=0.0, length_m=40.0, beam_m=10.0, surge_cms=450.0)
        wide = vessel(x_m=0.0, y_m=40.0, heading_deg=0.0, length_m=40.0, beam_m=80.0, surge_cms=450.0)
        self.assertGreater(hull_separation.separation_m(own(), narrow), hull_separation.separation_m(own(), wide))
        env = mmg_env.MaritimeRoutingEnv(
            destination_m=(2000.0, 0.0), step_s=0.2, max_steps=3, sea=flat_sea(),
            traffic=[overlapped], chart=deep_chart(),
        )
        env.reset(options={"heading_deg": 0.0})
        _, reward, terminated, truncated, info = env.step(np.array([0.0, 1.0]))
        self.assertTrue(info["collision"])
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertLess(reward, 0.0)
        self.assertLess(info["failure_reward"], 0.0)
        close = vessel(x_m=250.0, y_m=0.0, heading_deg=0.0, length_m=80.0, beam_m=20.0, surge_cms=450.0)
        gap = hull_separation.separation_m(own(), close)
        self.assertGreater(gap, 0.0)
        unsafe = encounter.decide(own(), [close], min_separation_m=gap + 5.0, horizon_s=30.0)
        safe = encounter.decide(own(), [close], min_separation_m=max(0.0, gap - 5.0), horizon_s=30.0)
        self.assertFalse(unsafe["safe"])
        self.assertIsNotNone(unsafe["override"])
        self.assertTrue(safe["safe"])
        self.assertIsNone(safe["override"])
        missing = vessel(x_m=200.0, y_m=0.0, heading_deg=0.0, length_m=40.0, beam_m=16.0)
        del missing["surge_cms"]
        del missing["sway_cms"]
        unavailable = encounter.decide(own(), [missing], min_separation_m=100.0, horizon_s=30.0)
        self.assertIsNone(unavailable["safe"])
        self.assertEqual(unavailable["override"], (0.0, -1.0))
        broken = vessel(heading_deg=float("nan"))
        invalid = encounter.decide(own(), [broken])
        self.assertEqual(invalid["status"], "invalid")
        self.assertIsNone(invalid["safe"])


if __name__ == "__main__":
    unittest.main()
