"""Rectangle separation for two hulls. This is not a chart or a COLREG model.

Each hull is a box in its heading frame, centred on its position. Units are
metres. A positive result is the gap between the boxes. A negative result is
the smallest overlap. No shoreline or traffic-lane data is used.
"""

import math


def _corners(hull):
    yaw = math.radians(hull["heading_deg"])
    forward = (math.cos(yaw), math.sin(yaw))
    right = (-math.sin(yaw), math.cos(yaw))
    half_l = 0.5 * float(hull["length_m"])
    half_b = 0.5 * float(hull["beam_m"])
    centre = (float(hull["x_m"]), float(hull["y_m"]))
    corners = []
    for along, across in ((-half_l, -half_b), (half_l, -half_b), (half_l, half_b), (-half_l, half_b)):
        corners.append((
            centre[0] + forward[0] * along + right[0] * across,
            centre[1] + forward[1] * along + right[1] * across,
        ))
    return corners


def _axes(corners):
    axes = []
    for index in range(2):
        x0, y0 = corners[index]
        x1, y1 = corners[(index + 1) % 4]
        edge = (x1 - x0, y1 - y0)
        length = math.hypot(edge[0], edge[1])
        if length <= 1.0e-9:
            continue
        axes.append((-edge[1] / length, edge[0] / length))
    return axes


def _axis_gap(a, b, axis):
    a_proj = [point[0] * axis[0] + point[1] * axis[1] for point in a]
    b_proj = [point[0] * axis[0] + point[1] * axis[1] for point in b]
    return max(min(a_proj), min(b_proj)) - min(max(a_proj), max(b_proj))


def _segment_gap(a0, a1, b0, b1):
    def point_gap(point, start, end):
        vx, vy = end[0] - start[0], end[1] - start[1]
        length2 = vx * vx + vy * vy
        if length2 <= 1.0e-12:
            return math.hypot(point[0] - start[0], point[1] - start[1])
        dot = ((point[0] - start[0]) * vx + (point[1] - start[1]) * vy) / length2
        dot = max(0.0, min(1.0, dot))
        nearest = (start[0] + dot * vx, start[1] + dot * vy)
        return math.hypot(point[0] - nearest[0], point[1] - nearest[1])

    return min(
        point_gap(a0, b0, b1),
        point_gap(a1, b0, b1),
        point_gap(b0, a0, a1),
        point_gap(b1, a0, a1),
    )


def separation_m(own, other):
    """Return the gap in metres. Negative means the rectangles overlap."""
    a = _corners(own)
    b = _corners(other)
    overlaps = []
    for axis in _axes(a) + _axes(b):
        gap = _axis_gap(a, b, axis)
        if gap > 0.0:
            break
        overlaps.append(gap)
    else:
        return max(overlaps) if overlaps else 0.0
    gap = float("inf")
    for index in range(4):
        for other_index in range(4):
            gap = min(gap, _segment_gap(a[index], a[(index + 1) % 4], b[other_index], b[(other_index + 1) % 4]))
    return gap
