"""Near-term encounter check for other vessels. This is not full COLREG.

Prediction moves each rectangle at its present ground velocity. Ground
velocity uses the same heading rotation as `route_telemetry.kinematic_speeds`.
The other vessel is not stepped with the MMG model. A positive rudder turns
toward the code `right` vector, which is +Y at heading 0. In the +X east,
+Y north frame that is a turn to port, so a starboard alteration is a
negative rudder command.

What is implemented, and only when position, heading, dimensions, and
velocity are finite:

- head-on: both bows are closing and headings differ by about 180 degrees;
  the own ship alters to starboard and slows
- overtaking: the own ship is catching a vessel ahead on a similar heading;
  it alters to starboard and slows
- crossing: headings differ. If the other vessel is on the geographic
  starboard side, the own ship alters to starboard and slows. If the other
  vessel is on the port side, speed is reduced and the rudder is not turned
  toward that vessel

What is not implemented: stand-on duty, narrow channels, traffic-separation
schemes, lights, shapes, and sound signals. `COLREG_COVERAGE["full_compliance"]`
is false. An empty traffic list is not a live all-clear, and a parsed packet
does not show that the UDP socket is connected.
"""

import math

import hull_separation as separation
import route_telemetry as telemetry

COLREG_COVERAGE = {
    "full_compliance": False,
    "implemented": (
        "head_on_alter_starboard",
        "overtaking_alter_starboard",
        "crossing_starboard_give_way",
        "crossing_port_side_slow_without_turning_toward",
    ),
    "not_implemented": (
        "stand_on",
        "narrow_channels",
        "traffic_separation_schemes",
        "lights_shapes_sound_signals",
    ),
}
HEAD_ON_DEG = 15.0
OVERTAKE_DEG = 22.5
LIVE_FEED = {
    "connected": False,
    "blocker": "The routing environment does not open the fleet UDP socket. A parsed MMG1 packet can be supplied as traffic in a test; that does not show live ingestion.",
}


def live_feed_status():
    return dict(LIVE_FEED)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _wrap(degrees):
    return (degrees + 180.0) % 360.0 - 180.0


def _ground(hull):
    speeds = telemetry.kinematic_speeds(hull.get("heading_deg"), hull.get("surge_cms"), hull.get("sway_cms"))
    return speeds["ground_east_m_s"], speeds["ground_north_m_s"]


def _moved(hull, east, north, dt):
    moved = dict(hull)
    moved["x_m"] = hull["x_m"] + east * dt
    moved["y_m"] = hull["y_m"] + north * dt
    return moved


def _body(own, other):
    dx = other["x_m"] - own["x_m"]
    dy = other["y_m"] - own["y_m"]
    yaw = math.radians(own["heading_deg"])
    forward = (math.cos(yaw), math.sin(yaw))
    right = (-math.sin(yaw), math.cos(yaw))
    along = dx * forward[0] + dy * forward[1]
    across = dx * right[0] + dy * right[1]
    return along, across


def _quality(vessel):
    if not isinstance(vessel, dict):
        return "invalid"
    if vessel.get("stale") is True:
        return "stale"
    for key in ("x_m", "y_m", "heading_deg", "length_m", "beam_m"):
        if key not in vessel or not _finite(vessel[key]):
            return "invalid"
        if key in ("length_m", "beam_m") and vessel[key] <= 0.0:
            return "invalid"
    if "surge_cms" not in vessel or "sway_cms" not in vessel:
        return "velocity_unavailable"
    if not _finite(vessel["surge_cms"]) or not _finite(vessel["sway_cms"]):
        return "invalid"
    return "ok"


def _classify(own, other, own_velocity, other_velocity):
    heading_gap = abs(_wrap(other["heading_deg"] - own["heading_deg"]))
    along, _across = _body(own, other)
    own_speed = math.hypot(*own_velocity)
    other_speed = math.hypot(*other_velocity)
    relative = (other_velocity[0] - own_velocity[0], other_velocity[1] - own_velocity[1])
    closing = relative[0] * (other["x_m"] - own["x_m"]) + relative[1] * (other["y_m"] - own["y_m"]) < 0.0
    if heading_gap >= 180.0 - HEAD_ON_DEG and along > 0.0 and closing:
        return "head_on"
    if heading_gap <= OVERTAKE_DEG and along > 0.0 and own_speed > other_speed + 0.5:
        return "overtaking"
    if heading_gap <= OVERTAKE_DEG:
        return "parallel"
    if own_speed > 0.2 and other_speed > 0.2:
        return "crossing"
    return "unknown"


def _starboard_side(own, other):
    """True when the other hull lies on geographic starboard."""
    _along, across = _body(own, other)
    return across < 0.0


def _predict(own, other, own_velocity, other_velocity, horizon_s):
    gap_now = separation.separation_m(own, other)
    worst = gap_now
    when = 0.0
    steps = max(1, int(math.ceil(horizon_s)))
    for second in range(1, steps + 1):
        dt = min(float(second), horizon_s)
        gap = separation.separation_m(
            _moved(own, own_velocity[0], own_velocity[1], dt),
            _moved(other, other_velocity[0], other_velocity[1], dt),
        )
        if gap < worst:
            worst = gap
            when = dt
    return gap_now, worst, when


def _none(status, reason, kind="unknown", stop=False):
    return {
        "status": status,
        "safe": None,
        "kind": kind,
        "override": (0.0, -1.0) if stop or status in ("stale", "invalid") else None,
        "cpa_gap_m": None,
        "tcpa_s": None,
        "reason": reason,
    }


def decide(own, traffic, min_separation_m=100.0, horizon_s=180.0):
    """Return a helm override when the supplied traffic is unsafe or unusable.

    `override` is an action pair `(rudder fraction, ordered-speed fraction)`
    or None. `safe` is True only when every supplied vessel has a finite
    velocity and the predicted rectangle gap stays at least `min_separation_m`.
    """
    if not traffic:
        return {"status": "none", "safe": None, "kind": "none", "override": None, "cpa_gap_m": None, "tcpa_s": None, "reason": "no traffic was supplied"}
    if not _finite(min_separation_m) or min_separation_m < 0.0 or not _finite(horizon_s) or horizon_s <= 0.0:
        return _none("invalid", "separation or horizon is invalid")
    if _quality(own) != "ok":
        return _none("invalid", "own ship position, heading, dimensions, or velocity is unusable")
    qualities = [_quality(vessel) for vessel in traffic]
    if "stale" in qualities:
        return _none("stale", "stale vessel data; not treated as safe")
    if "invalid" in qualities:
        return _none("invalid", "malformed or non-finite vessel data; not treated as safe")
    own_velocity = _ground(own)
    if own_velocity[0] is None:
        return _none("invalid", "own ground velocity is unavailable")
    usable = []
    missing_velocity = False
    for vessel, quality in zip(traffic, qualities):
        if quality == "velocity_unavailable":
            missing_velocity = True
            try:
                gap = separation.separation_m(own, vessel)
            except (KeyError, TypeError, ValueError):
                return _none("invalid", "vessel footprint is unusable")
            if gap < min_separation_m:
                stopped = _none("velocity_unavailable", "nearby vessel has no velocity; not treated as safe", stop=True)
                stopped["cpa_gap_m"] = gap
                return stopped
            continue
        other_velocity = _ground(vessel)
        _gap_now, worst, when = _predict(own, vessel, own_velocity, other_velocity, horizon_s)
        usable.append({
            "kind": _classify(own, vessel, own_velocity, other_velocity),
            "gap": worst,
            "when": when,
            "vessel": vessel,
            "risk": worst < min_separation_m,
        })
    risks = [item for item in usable if item["risk"]]
    if risks:
        closest = min(risks, key=lambda item: item["gap"])
        kind = closest["kind"]
        if kind == "crossing" and not _starboard_side(own, closest["vessel"]):
            rudder, speed = 0.0, -1.0
        else:
            rudder, speed = -1.0, -0.5
        return {
            "status": "risk",
            "safe": False,
            "kind": kind,
            "override": (rudder, speed),
            "cpa_gap_m": closest["gap"],
            "tcpa_s": closest["when"],
            "reason": "predicted separation enters the safety margin",
        }
    if missing_velocity:
        return {
            "status": "velocity_unavailable",
            "safe": None,
            "kind": "unknown",
            "override": None,
            "cpa_gap_m": None,
            "tcpa_s": None,
            "reason": "vessel velocity is missing; not treated as safe",
        }
    nearest = min(usable, key=lambda item: item["gap"])
    return {
        "status": "clear",
        "safe": True,
        "kind": nearest["kind"],
        "override": None,
        "cpa_gap_m": nearest["gap"],
        "tcpa_s": nearest["when"],
        "reason": "predicted gap stays outside the minimum separation",
    }
