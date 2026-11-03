import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import hull_separation as separation


def hull(x, y, heading=0.0, length=300.0, beam=42.0):
    return {"x_m": x, "y_m": y, "heading_deg": heading, "length_m": length, "beam_m": beam}


class HullSeparationTest(unittest.TestCase):
    def test_clear_passage_near_miss_and_overlap(self):
        clear = separation.separation_m(hull(0, 0), hull(800, 0))
        self.assertGreater(clear, 50.0)
        near = separation.separation_m(hull(0, 0), hull(340, 0))
        self.assertGreater(near, 0.0)
        self.assertLess(near, 50.0)
        overlap = separation.separation_m(hull(0, 0), hull(100, 0))
        self.assertLess(overlap, 0.0)
        touching = separation.separation_m(hull(0, 0), hull(300, 0))
        self.assertAlmostEqual(touching, 0.0, places=6)

    def test_beam_and_heading_change_the_gap(self):
        ahead = separation.separation_m(hull(0, 0, 0), hull(0, 200, 0))
        self.assertGreater(ahead, 100.0)
        crossed = separation.separation_m(hull(0, 0, 0), hull(0, 0, 90))
        self.assertLess(crossed, 0.0)


if __name__ == "__main__":
    unittest.main()
