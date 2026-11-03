import math
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
import fleet_state
import mmg_physics as mmg


def hull(x_cm, y_cm, heading_deg, length_cm=30000.0, beam_cm=4000.0):
    values = [0.0] * 18
    values[0] = x_cm
    values[1] = y_cm
    values[2] = heading_deg
    values[9] = length_cm
    values[10] = beam_cm
    return values


def packet(seq, ships, count=None):
    declared = len(ships) if count is None else count
    header = mmg.HEADER.pack(mmg.REQ, seq, declared, 0.02, 12.0, 400.0, 30.0, 25.0, 40.0, 40.0, 30.0)
    body = b"".join(mmg.SHIP.pack(index, *values) for index, values in enumerate(ships))
    return header + body


class FleetStateTest(unittest.TestCase):
    def test_two_ships_report_clear_passage_and_overlap(self):
        clear = fleet_state.parse_mmg1(packet(3, [hull(0.0, 0.0, 0.0), hull(80000.0, 0.0, 0.0)]))
        self.assertEqual(clear["seq"], 3)
        self.assertEqual(clear["obstacles"], [])
        self.assertEqual(clear["missing"], fleet_state.MISSING_FIELDS)
        gap = fleet_state.pairwise_separation(clear["ships"])
        self.assertEqual(len(gap), 1)
        self.assertGreater(gap[0][2], 50.0)

        overlap = fleet_state.parse_mmg1(packet(4, [hull(0.0, 0.0, 0.0), hull(10000.0, 0.0, 0.0)]))
        self.assertLess(fleet_state.pairwise_separation(overlap["ships"])[0][2], 0.0)

    def test_stale_sequence_and_a_short_packet_are_rejected(self):
        payload = packet(5, [hull(0.0, 0.0, 0.0), hull(80000.0, 0.0, 90.0)])
        fleet_state.parse_mmg1(payload, last_seq=4)
        with self.assertRaises(fleet_state.StaleFleetState):
            fleet_state.parse_mmg1(payload, last_seq=5)
        short = packet(6, [hull(0.0, 0.0, 0.0)], count=2)
        with self.assertRaises(fleet_state.IncompleteFleetState):
            fleet_state.parse_mmg1(short)
        broken = bytearray(packet(7, [hull(0.0, 0.0, 0.0)]))
        # Heading sits in the first ship float block; replace it with a NaN.
        nan = struct.pack("<f", float("nan"))
        heading_at = mmg.HEADER.size + 4 + 8
        broken[heading_at:heading_at + 4] = nan
        with self.assertRaises(fleet_state.IncompleteFleetState):
            fleet_state.parse_mmg1(bytes(broken))
        self.assertTrue(math.isnan(struct.unpack_from("<f", bytes(broken), heading_at)[0]))


if __name__ == "__main__":
    unittest.main()
