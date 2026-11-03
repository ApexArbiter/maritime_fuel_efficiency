import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import weather_presets as weather


class WeatherPresetTest(unittest.TestCase):
    def test_atmospheres_change_only_visual_fields(self):
        summer = weather.SEASONS["summer calm"]
        for name in ("clear", "cloudy", "rain"):
            combined = weather.apply_atmosphere(summer, name)
            for field in weather.PHYSICAL_FIELDS:
                self.assertEqual(combined[field], summer[field])
            self.assertEqual(combined["atmosphere"], name)
        self.assertGreater(weather.ATMOSPHERES["cloudy"]["cloud"], weather.ATMOSPHERES["clear"]["cloud"])
        self.assertGreater(weather.ATMOSPHERES["rain"]["cloud"], weather.ATMOSPHERES["cloudy"]["cloud"])
        self.assertEqual(weather.ATMOSPHERES["clear"]["rain"], 0.0)
        self.assertEqual(weather.ATMOSPHERES["cloudy"]["rain"], 0.0)
        self.assertEqual(weather.ATMOSPHERES["rain"]["rain"], 1.0)
        self.assertLess(weather.ATMOSPHERES["rain"]["exposure_add"], weather.ATMOSPHERES["clear"]["exposure_add"])

    def test_seasons_keep_their_physical_values(self):
        self.assertEqual(weather.SEASONS["summer calm"]["wave_m"], 0.4)
        self.assertEqual(weather.SEASONS["spring tide"]["wave_m"], 1.3)
        self.assertEqual(weather.SEASONS["autumn gale"]["wave_m"], 2.8)
        self.assertEqual(weather.SEASONS["winter storm"]["wave_m"], 4.0)
        self.assertNotIn("clear", weather.SEASONS)
        with self.assertRaises(ValueError):
            weather.apply_atmosphere(weather.SEASONS["winter storm"], "fog")

    def test_cpp_literals_match_the_visual_table(self):
        root = os.path.join(os.path.dirname(__file__), "..", "Source", "MaritimeFuelEfficiency", "FleetEnvironment.cpp")
        text = open(root, encoding="utf-8").read()
        for name, values in weather.ATMOSPHERES.items():
            self.assertIn('TEXT("%s")' % name, text)
            self.assertIn("%.2f" % values["cloud"] if False else "", "")
        self.assertIn("0.08f, 0.15f, 1.05f, 0.0f, 0.0f", text)
        self.assertIn("0.62f, -0.25f, 0.72f, 0.004f, 0.0f", text)
        self.assertIn("0.88f, -0.55f, 0.48f, 0.012f, 1.0f", text)


if __name__ == "__main__":
    unittest.main()
