"""Synthetic navigable-water checks. These fixtures are not a real chart."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import mmg_env
import navigable_water as water


def hull(x=0.0, y=0.0, heading=0.0, length=300.0, beam=42.8):
    return {
        "x_m": x,
        "y_m": y,
        "heading_deg": heading,
        "length_m": length,
        "beam_m": beam,
        "surge_cms": 450.0,
        "sway_cms": 0.0,
    }


def chart(land=None, depth=40.0, shoals=None):
    body = {"source": "synthetic_fixture", "land": land or []}
    if depth is not None:
        body["default_depth_m"] = depth
    if shoals:
        body["shoals"] = shoals
    return body


WALL = [(200.0, -1000.0), (230.0, -1000.0), (230.0, 1000.0), (200.0, 1000.0)]
BOW = [(140.0, -40.0), (200.0, -40.0), (200.0, 40.0), (140.0, 40.0)]
BANK_NORTH = [(-500.0, 80.0), (2000.0, 80.0), (2000.0, 500.0), (-500.0, 500.0)]
BANK_SOUTH = [(-500.0, -500.0), (2000.0, -500.0), (2000.0, -80.0), (-500.0, -80.0)]


class NavigableWaterTest(unittest.TestCase):
    def test_clear_water_channel_land_depth_and_missing_data(self):
        clear = water.assess(chart(), hull(), 14.5, 2.0)
        self.assertEqual(clear["status"], "clear")
        self.assertTrue(clear["safe"])
        self.assertEqual(clear["squat"], "not_modeled")
        self.assertAlmostEqual(clear["required_depth_m"], 16.5)

        crossed = water.assess(chart([WALL]), hull(500.0), 14.5, 2.0, previous=hull(0.0))
        self.assertEqual(crossed["status"], "land")
        self.assertFalse(crossed["safe"])
        self.assertFalse(water._point_in_ring((500.0, 0.0), WALL))

        shallow = water.assess(chart(depth=16.0), hull(), 14.5, 2.0)
        self.assertEqual(shallow["status"], "shallow")
        self.assertFalse(shallow["safe"])
        self.assertAlmostEqual(shallow["required_depth_m"], 16.5)

        bow = water.assess(chart([BOW]), hull(), 14.5, 2.0)
        self.assertEqual(bow["status"], "land")
        self.assertFalse(water._point_in_ring((0.0, 0.0), BOW))
        self.assertTrue(water._point_in_ring((150.0, 21.0), BOW))

        missing = water.assess(None, hull(), 14.5, 2.0)
        self.assertEqual(missing["status"], "unavailable")
        self.assertIsNone(missing["safe"])
        invalid = water.assess({"land": "not-a-ring", "default_depth_m": float("nan")}, hull(), 14.5, 2.0)
        self.assertEqual(invalid["status"], "invalid")
        self.assertIsNone(invalid["safe"])
        unknown_depth = water.assess({"source": "synthetic_fixture", "land": []}, hull(), 14.5, 2.0)
        self.assertEqual(unknown_depth["status"], "unknown")
        self.assertIsNone(unknown_depth["safe"])

        channel = water.assess(chart([BANK_NORTH, BANK_SOUTH], depth=30.0), hull(), 14.5, 2.0)
        self.assertEqual(channel["status"], "clear")
        self.assertTrue(channel["safe"])

    def test_environment_stops_before_land_or_shallow_water(self):
        ahead = chart([[(152.0, -100.0), (400.0, -100.0), (400.0, 100.0), (152.0, 100.0)]])
        blocked = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=5, sea=_flat(), chart=ahead)
        blocked.reset(options={"heading_deg": 0.0})
        open_water = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=5, sea=_flat(), chart=chart())
        open_water.reset(options={"heading_deg": 0.0})
        _, _, _, _, free = open_water.step(np.array([0.0, 1.0]))
        _, reward, terminated, truncated, info = blocked.step(np.array([0.0, 1.0]))
        self.assertEqual(info["termination"], "land")
        self.assertTrue(terminated)
        self.assertFalse(truncated)
        self.assertLess(reward, 0.0)
        self.assertFalse(info["arrived"])
        self.assertLess(info["x_m"], free["x_m"])
        self.assertTrue(all(corner[0] < 152.0 for corner in water.separation._corners(hull(info["x_m"], info["y_m"]))))

        shallow = mmg_env.MaritimeRoutingEnv(
            destination_m=(2000.0, 0.0), step_s=1.0, max_steps=3, sea=_flat(),
            chart=chart(depth=10.0), under_keel_clearance_m=2.0,
        )
        shallow.reset(options={"heading_deg": 0.0})
        _, reward, terminated, _, info = shallow.step(np.array([0.0, 1.0]))
        self.assertEqual(info["termination"], "shallow")
        self.assertTrue(terminated)
        self.assertEqual(info["x_m"], 0.0)
        self.assertEqual(info["fuel_t"], 0.0)
        self.assertLess(reward, 0.0)
        self.assertEqual(info["squat"], "not_modeled")
        self.assertAlmostEqual(info["required_depth_m"], 16.5)

        channel = mmg_env.MaritimeRoutingEnv(
            destination_m=(2000.0, 0.0), step_s=1.0, max_steps=3, sea=_flat(),
            chart=chart([BANK_NORTH, BANK_SOUTH], depth=30.0),
        )
        channel.reset(options={"heading_deg": 0.0})
        _, _, terminated, _, info = channel.step(np.array([0.0, 1.0]))
        self.assertEqual(info["termination"], "running")
        self.assertFalse(terminated)
        self.assertTrue(info["navigable"])
        self.assertGreater(info["x_m"], 3.0)

        bare = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=0.2, max_steps=3, sea=_flat())
        bare.reset(options={"heading_deg": 0.0})
        _, _, terminated, _, info = bare.step(np.array([0.0, 1.0]))
        self.assertIsNone(info["navigable"])
        self.assertEqual(info["chart_status"], "unavailable")
        self.assertFalse(terminated)
        self.assertIn("not checked", info["warning"])

        broken = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=3, chart={"land": []})
        broken.reset(options={"heading_deg": 0.0})
        held = broken.ship
        _, reward, terminated, _, info = broken.step(np.array([0.0, 1.0]))
        self.assertEqual(info["termination"], "chart_unknown")
        self.assertIsNone(info["navigable"])
        self.assertTrue(terminated)
        self.assertLess(reward, 0.0)
        self.assertEqual(broken.ship[16], held[16])
        self.assertEqual(mmg_env.OBSERVATION_DIM, 12)
        self.assertEqual(mmg_env.ACTION_DIM, 2)


def _flat():
    return {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}


if __name__ == "__main__":
    unittest.main()
