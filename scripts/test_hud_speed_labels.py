"""HUD speed labels follow the telemetry convention. This does not launch Unreal."""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import mmg_physics as mmg
import route_telemetry as telemetry

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SHIP = os.path.join(ROOT, "Source", "MaritimeFuelEfficiency", "FleetShip.cpp")
HUD = os.path.join(ROOT, "Source", "MaritimeFuelEfficiency", "FleetHUD.cpp")
ENVIRONMENT = os.path.join(ROOT, "Source", "MaritimeFuelEfficiency", "FleetEnvironment.cpp")


class HudSpeedLabelTest(unittest.TestCase):
    def test_display_knots_match_an_independent_calculation(self):
        surge_cms, sway_cms = 500.0, 0.0
        current_cms, current_deg = 100.0, 90.0
        knots_per_ms = 1.0 / mmg.KNOT_MS
        ground_east, ground_north = 5.0, 0.0
        current_east = math.cos(math.radians(current_deg)) * (current_cms / 100.0)
        current_north = math.sin(math.radians(current_deg)) * (current_cms / 100.0)
        water_east = ground_east - current_east
        water_north = ground_north - current_north
        speeds = telemetry.kinematic_speeds(0.0, surge_cms, sway_cms, current_cms, current_deg)
        self.assertAlmostEqual(speeds["sog_m_s"], math.hypot(ground_east, ground_north), places=6)
        self.assertAlmostEqual(speeds["stw_m_s"], math.hypot(water_east, water_north), places=6)
        self.assertAlmostEqual(speeds["sog_m_s"] * knots_per_ms, 5.0 * knots_per_ms, places=4)
        self.assertNotAlmostEqual(speeds["stw_m_s"], speeds["sog_m_s"], places=3)
        self.assertIsNone(telemetry.kinematic_speeds(0.0, 0.0, 0.0, 0.0, 0.0)["cog_deg"])

    def test_hud_source_names_each_quantity_and_keeps_the_motion_update(self):
        with open(SHIP, encoding="utf-8") as handle:
            ship = handle.read()
        with open(HUD, encoding="utf-8") as handle:
            hud = handle.read()
        self.assertIn("KnotsPerMs = 1.943844f", ship)
        self.assertIn("CogMinMs = 0.05f", ship)
        self.assertIn("EastMs - CurrentEast", ship)
        self.assertIn("NorthMs - CurrentNorth", ship)
        self.assertIn("(Forward * SurgeCms + Right * SwayCms)", ship)
        self.assertIn("HeadingError * 1.15f", ship)
        for label in ("surge", "STW", "SOG", "COG", "heading", "N/A"):
            self.assertIn(label, hud)
        self.assertNotIn("%5.1f kn   heading", hud)
        self.assertIn("if (bCurrentValid && FMath::IsFinite(CurrentMs)", ship)
        with open(ENVIRONMENT, encoding="utf-8") as handle:
            environment = handle.read()
        self.assertIn("surge_kn %.1f", environment)
        self.assertNotIn("CONTROL SHIP %s kn %.1f", environment)


if __name__ == "__main__":
    unittest.main()
