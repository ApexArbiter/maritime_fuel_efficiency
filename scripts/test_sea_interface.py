"""Wind and current reach the existing physics clock. Visual weather does not."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import mmg_env
import mmg_physics as mmg
import weather_presets as weather


def zero():
    return {"wind_ms": 0.0, "wind_deg": 0.0, "current_ms": 0.0, "current_deg": 0.0, "wave_m": 0.0, "wave_deg": 0.0}


def clock(sea, time=0.0):
    return {
        "time": time,
        "wind_cms": sea["wind_ms"] * 100.0,
        "wind_deg": sea["wind_deg"],
        "current_cms": sea["current_ms"] * 100.0,
        "current_deg": sea["current_deg"],
        "wave_cm": sea["wave_m"] * 100.0,
        "wave_deg": sea["wave_deg"],
    }


def sail(sea, seconds=4.0):
    ship = mmg_env.reference_ship()
    state = clock(sea)
    steps = int(round(seconds / 0.02))
    for _ in range(steps):
        ship, _, _, _, _ = mmg.integrate(ship, state, 0.02)
        ship = mmg_env.advance_position(ship, 0.02)
    return ship, state


class SeaInterfaceTest(unittest.TestCase):
    def test_zero_input_matches_itself_and_current_follows_the_frame(self):
        self.assertEqual(mmg_env.INNER_DT_S, 0.02)
        calm_a, time_a = sail(zero())
        calm_b, time_b = sail(zero())
        self.assertEqual(calm_a, calm_b)
        self.assertAlmostEqual(time_a["time"], 4.0, places=6)
        self.assertAlmostEqual(time_b["time"], 4.0, places=6)
        self.assertLess(abs(calm_a[2]), 5.0)
        current = zero()
        current["current_ms"] = 1.5
        current["current_deg"] = 90.0
        pushed, _ = sail(current)
        self.assertGreater(pushed[2], calm_a[2] + 20.0)
        self.assertGreater(pushed[17], calm_a[17] + 50.0)
        east, north = mmg.direction(90.0, 150.0)
        self.assertAlmostEqual(east, 0.0, places=6)
        self.assertAlmostEqual(north, 150.0, places=6)

    def test_wind_changes_sway_and_visual_weather_is_not_a_physics_input(self):
        wind = zero()
        wind["wind_ms"] = 15.0
        wind["wind_deg"] = 90.0
        calm, _ = sail(zero(), 8.0)
        blown, _ = sail(wind, 8.0)
        # The existing lateral wind force is small beside this displacement.
        # Eight seconds still moves sway the same way as the +Y wind vector.
        self.assertGreater(blown[2], calm[2] + 0.2)

        env = mmg_env.MaritimeRoutingEnv(destination_m=(2000.0, 0.0), step_s=1.0, max_steps=3, sea=zero())
        env.reset(options={"heading_deg": 0.0})
        held = dict(env.clock)
        env.set_sea(wind)
        self.assertEqual(env.clock["wind_cms"], 1500.0)
        self.assertEqual(env.clock["current_cms"], 0.0)
        with self.assertRaises(ValueError):
            env.set_sea({"cloud": 1.0, "rain": 1.0})
        with self.assertRaises(ValueError):
            env.set_sea(dict(wind, wind_ms=float("nan")))
        with self.assertRaises(ValueError):
            env.set_sea(dict(wind, current_ms=-1.0))
        self.assertEqual(env.clock["wind_cms"], 1500.0)
        self.assertEqual(held["current_cms"], 0.0)

        physical = dict(weather.SEASONS["summer calm"])
        visual = weather.apply_atmosphere(physical, "rain")
        for field in weather.PHYSICAL_FIELDS:
            self.assertEqual(visual[field], physical[field])
        self.assertEqual(visual["atmosphere"], "rain")
        self.assertEqual(mmg_env.OBSERVATION_DIM, 12)
        self.assertEqual(mmg_env.ACTION_DIM, 2)


if __name__ == "__main__":
    unittest.main()
