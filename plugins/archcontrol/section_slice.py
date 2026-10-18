# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Plane/triangle intersection for an editable section outline, in metres."""
import math


def plane_basis(point, normal):
    point = tuple(float(v) for v in point)
    normal = tuple(float(v) for v in normal)
    if len(point) != 3 or len(normal) != 3 or not all(math.isfinite(v) for v in (*point, *normal)):
        raise ValueError("Rovina řezu nemá platné souřadnice.")
    length = math.sqrt(sum(v*v for v in normal))
    if length < 1e-12:
        raise ValueError("Rovina řezu má nulovou normálu.")
    return point, tuple(v / length for v in normal)


def triangle_segment(triangle, point, normal, tolerance=1e-7):
    """A crossing or an edge on the plane; isolated touches have no segment.

    Coplanar triangles are omitted: callers use the original face boundary
    instead, avoiding triangulation diagonals in coplanar faces.
    """
    distances = [sum(normal[i]*(p[i]-point[i]) for i in range(3)) for p in triangle]
    zero = [abs(d) <= tolerance for d in distances]
    if all(zero) or all(d > tolerance for d in distances) or all(d < -tolerance for d in distances):
        return None
    points = []
    for vertex, distance, on_plane in zip(triangle, distances, zero):
        if on_plane:
            points.append(tuple(vertex[i]-distance*normal[i] for i in range(3)))
    for a, b in ((0, 1), (1, 2), (2, 0)):
        if not zero[a] and not zero[b] and distances[a]*distances[b] < 0:
            t = distances[a] / (distances[a]-distances[b])
            points.append(tuple(triangle[a][i] + t*(triangle[b][i]-triangle[a][i]) for i in range(3)))
    if len(points) != 2 or sum((points[0][i]-points[1][i])**2 for i in range(3)) <= tolerance**2:
        return None
    return tuple(points)
