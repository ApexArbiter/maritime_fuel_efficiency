"""Navigable-water checks in the simulation X/Y frame.

The frame matches `advance_position`: metres, +X east and +Y north of that
frame. It is not latitude or longitude. This module does not contain a real
coastline, a bathymetry survey, or a geographic chart. Callers pass a chart
dict or None.

A chart dict may contain:

- `source`: `"synthetic_fixture"` for the tests in this repository
- `land`: closed rings, each a list of `(x, y)` metres
- `default_depth_m`: water depth used where no shoal applies
- `shoals`: rectangles `{xmin, xmax, ymin, ymax, depth_m}`

`None` means the chart is unavailable. Unavailable and invalid charts are
unknown, not proof that the water is safe. Squat is not modeled: the required
depth is the static draft plus `under_keel_clearance_m` (default 2.0 m).
"""

import math

import hull_separation as separation

UNDER_KEEL_CLEARANCE_M = 2.0
SQUAT = "not_modeled"
_BLOCKING = ("land", "shallow", "invalid", "unknown")


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _ring_valid(ring):
    if not isinstance(ring, (list, tuple)) or len(ring) < 3:
        return False
    return all(isinstance(point, (list, tuple)) and len(point) == 2 and _finite(point[0]) and _finite(point[1]) for point in ring)


def _on_segment(point, start, end):
    px, py = point
    x0, y0 = start
    x1, y1 = end
    if px < min(x0, x1) - 1.0e-8 or px > max(x0, x1) + 1.0e-8:
        return False
    if py < min(y0, y1) - 1.0e-8 or py > max(y0, y1) + 1.0e-8:
        return False
    return True


def _segments_intersect(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if o1 * o2 < 0.0 and o3 * o4 < 0.0:
        return True
    if abs(o1) <= 1.0e-8 and _on_segment(c, a, b):
        return True
    if abs(o2) <= 1.0e-8 and _on_segment(d, a, b):
        return True
    if abs(o3) <= 1.0e-8 and _on_segment(a, c, d):
        return True
    if abs(o4) <= 1.0e-8 and _on_segment(b, c, d):
        return True
    return False


def _point_in_ring(point, ring):
    x, y = point
    inside = False
    count = len(ring)
    for index in range(count):
        x0, y0 = ring[index]
        x1, y1 = ring[(index + 1) % count]
        if (y0 > y) != (y1 > y):
            cross = (x1 - x0) * (y - y0) / (y1 - y0) + x0
            if x < cross:
                inside = not inside
    return inside


def _depth_m(chart, point):
    found = None
    for shoal in chart.get("shoals") or []:
        if point[0] < shoal["xmin"] or point[0] > shoal["xmax"] or point[1] < shoal["ymin"] or point[1] > shoal["ymax"]:
            continue
        found = shoal["depth_m"] if found is None else min(found, shoal["depth_m"])
    if found is not None:
        return found
    if "default_depth_m" in chart and _finite(chart["default_depth_m"]):
        return float(chart["default_depth_m"])
    return None


def _chart_error(chart):
    if not isinstance(chart, dict):
        return "chart is not a dict"
    land = chart.get("land", [])
    if not isinstance(land, (list, tuple)) or not all(_ring_valid(ring) for ring in land):
        return "land rings are missing or invalid"
    shoals = chart.get("shoals", [])
    if not isinstance(shoals, (list, tuple)):
        return "shoals are invalid"
    for shoal in shoals:
        if not isinstance(shoal, dict):
            return "shoal is invalid"
        for key in ("xmin", "xmax", "ymin", "ymax", "depth_m"):
            if key not in shoal or not _finite(shoal[key]):
                return "shoal field %s is missing or non-finite" % key
        if shoal["xmin"] > shoal["xmax"] or shoal["ymin"] > shoal["ymax"]:
            return "shoal bounds are reversed"
    if "default_depth_m" in chart and not _finite(chart["default_depth_m"]):
        return "default depth is non-finite"
    return None


def _touches_land(chart, points, segments):
    for ring in chart.get("land") or []:
        for point in points:
            if _point_in_ring(point, ring):
                return True
        count = len(ring)
        for index in range(count):
            edge = (ring[index], ring[(index + 1) % count])
            for segment in segments:
                if _segments_intersect(segment[0], segment[1], edge[0], edge[1]):
                    return True
    return False


def assess(chart, hull, draft_m, clearance_m=UNDER_KEEL_CLEARANCE_M, previous=None):
    """Classify one hull pose. `safe` is True only for a clear, complete chart."""
    result = {
        "status": "unavailable",
        "safe": None,
        "squat": SQUAT,
        "required_depth_m": None,
        "depth_m": None,
        "reason": "chart unavailable; navigable water was not checked",
    }
    if chart is None:
        return result
    if not _finite(draft_m) or draft_m < 0.0 or not _finite(clearance_m) or clearance_m < 0.0:
        result["status"] = "invalid"
        result["reason"] = "draft or under-keel clearance is missing or invalid"
        return result
    error = _chart_error(chart)
    if error is not None:
        result["status"] = "invalid"
        result["reason"] = error
        return result
    try:
        corners = separation._corners(hull)
    except (KeyError, TypeError, ValueError):
        result["status"] = "invalid"
        result["reason"] = "hull footprint is incomplete"
        return result
    if not all(_finite(value) for point in corners for value in point):
        result["status"] = "invalid"
        result["reason"] = "hull footprint is non-finite"
        return result
    centre = (float(hull["x_m"]), float(hull["y_m"]))
    points = corners + [centre]
    segments = [(corners[index], corners[(index + 1) % 4]) for index in range(4)]
    if previous is not None:
        try:
            before = separation._corners(previous)
            before_centre = (float(previous["x_m"]), float(previous["y_m"]))
        except (KeyError, TypeError, ValueError):
            result["status"] = "invalid"
            result["reason"] = "previous hull footprint is incomplete"
            return result
        segments.extend((before[index], corners[index]) for index in range(4))
        segments.append((before_centre, centre))
    if _touches_land(chart, points, segments):
        result["status"] = "land"
        result["safe"] = False
        result["reason"] = "land collision"
        result["required_depth_m"] = float(draft_m) + float(clearance_m)
        return result
    depths = [_depth_m(chart, point) for point in points]
    result["required_depth_m"] = float(draft_m) + float(clearance_m)
    if any(depth is None for depth in depths):
        result["status"] = "unknown"
        result["reason"] = "chart depth is unknown"
        return result
    result["depth_m"] = min(depths)
    if result["depth_m"] < result["required_depth_m"]:
        result["status"] = "shallow"
        result["safe"] = False
        result["reason"] = "insufficient depth"
        return result
    result["status"] = "clear"
    result["safe"] = True
    result["reason"] = "clear navigable water"
    return result


def blocking(verdict):
    return verdict["status"] in _BLOCKING
