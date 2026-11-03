"""Read hulls from an MMG1 request without integrating or steering.

The live packet already carries each ship's position, heading, hull
dimensions, surge, and sway. It does not carry shore, depth, or chart
obstacles. This parser does not open a socket and does not claim COLREG
compliance. The routing environment still starts with an empty traffic list.
"""

import math

import mmg_physics as mmg
import hull_separation as separation

MISSING_FIELDS = ("shore", "depth", "chart_obstacles")


class StaleFleetState(ValueError):
    """The sequence is older than or equal to one already accepted."""


class IncompleteFleetState(ValueError):
    """The packet is short, malformed, or contains a non-finite hull."""


def parse_mmg1(payload, last_seq=None):
    if len(payload) < mmg.HEADER.size or payload[:4] != mmg.REQ:
        raise IncompleteFleetState("not an MMG1 request")
    _magic, seq, count, _dt, sim_time, *_sea = mmg.HEADER.unpack_from(payload, 0)
    if last_seq is not None and seq <= last_seq:
        raise StaleFleetState("sequence %s is not newer than %s" % (seq, last_seq))
    need = mmg.HEADER.size + count * mmg.SHIP.size
    if len(payload) < need:
        raise IncompleteFleetState("need %d bytes for %d ships, have %d" % (need, count, len(payload)))
    ships = []
    offset = mmg.HEADER.size
    for _index in range(count):
        values = mmg.SHIP.unpack_from(payload, offset)
        offset += mmg.SHIP.size
        ship_id = values[0]
        x_cm, y_cm, yaw_deg = values[1], values[2], values[3]
        surge_cms, sway_cms = values[4], values[5]
        length_cm, beam_cm = values[10], values[11]
        numbers = (x_cm, y_cm, yaw_deg, surge_cms, sway_cms, length_cm, beam_cm)
        if not all(math.isfinite(number) for number in numbers):
            raise IncompleteFleetState("non-finite hull %s" % ship_id)
        ships.append({
            "id": int(ship_id),
            "x_m": x_cm / 100.0,
            "y_m": y_cm / 100.0,
            "heading_deg": float(yaw_deg),
            "surge_cms": float(surge_cms),
            "sway_cms": float(sway_cms),
            "length_m": length_cm / 100.0,
            "beam_m": beam_cm / 100.0,
        })
    return {
        "seq": int(seq),
        "sim_time_s": float(sim_time),
        "ships": ships,
        "obstacles": [],
        "missing": MISSING_FIELDS,
    }


def traffic_from_parsed(parsed, own_id=None):
    """Copy parsed hulls into the routing traffic list. This does not read a socket."""
    if not isinstance(parsed, dict) or "ships" not in parsed:
        raise IncompleteFleetState("parsed fleet state has no ships")
    traffic = []
    for ship in parsed["ships"]:
        if own_id is not None and ship.get("id") == own_id:
            continue
        traffic.append(dict(ship))
    return traffic


def pairwise_separation(ships):
    gaps = []
    for left in range(len(ships)):
        for right in range(left + 1, len(ships)):
            gaps.append((ships[left]["id"], ships[right]["id"], separation.separation_m(ships[left], ships[right])))
    return gaps
