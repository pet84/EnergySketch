# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Ruby zone report aggregation; the host supplies measured solid volumes."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from .core import build_zone_numbers
import math


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


def _inside(point, triangles):
    """Parity ray, deduplicated at shared triangulation edges/vertices."""
    direction = (1., .3713906763541037, .127831)
    hits = []
    for a, b, c in triangles:
        e1, e2 = _sub(b, a), _sub(c, a)
        p = _cross(direction, e2)
        det = _dot(e1, p)
        if abs(det) < 1e-14:
            continue
        tvec = _sub(point, a)
        u = _dot(tvec, p) / det
        if not -1e-10 <= u <= 1 + 1e-10:
            continue
        q = _cross(tvec, e1)
        v = _dot(direction, q) / det
        if v < -1e-10 or u + v > 1 + 1e-10:
            continue
        distance = _dot(e2, q) / det
        if distance > 1e-10:
            hits.append(distance)
    unique = []
    for value in sorted(hits):
        if not unique or abs(value - unique[-1]) > 1e-8 * max(1., abs(value)):
            unique.append(value)
    return bool(len(unique) % 2)


def solid_volume_triangles(triangles):
    return solid_volume_faces([{"loops": [triangle], "triangles": [triangle]} for triangle in triangles])


def solid_volume_faces(faces):
    """Closed manifold volume, tolerating reversed face normals.

    Orient a temporary polygon graph only; never change model winding,
    front/back paint or export normals. Disconnected cavity shells subtract
    by containment parity. Open, degenerate and nonorientable meshes return
    None. Source unit is metres, output m³.

    Ear clipping may omit collinear boundary points, so adjacency must use
    the original polygon loops rather than the triangulation's edge set.
    """
    faces = list(faces)
    if not faces:
        return None
    edges = defaultdict(list)
    for i, face in enumerate(faces):
        if not face["triangles"]:
            return None
        outer = None
        for raw in face["loops"]:
            loop = [tuple(p) for p in raw]
            if len(loop) < 3 or any(not math.isfinite(v) for point in loop for v in point):
                return None
            vectors = [_cross(_sub(a, loop[0]), _sub(b, loop[0])) for a, b in zip(loop, [*loop[1:], loop[0]])]
            normal = tuple(math.fsum(v[j] for v in vectors) for j in range(3))
            if outer is None:
                outer = normal
            elif _dot(outer, normal) > 0:
                loop.reverse()
            for first, second in zip(loop, [*loop[1:], loop[0]]):
                edges[tuple(sorted((first, second)))].append((i, first < second))
    if any(len(items) != 2 for items in edges.values()):
        return None
    graph = defaultdict(list)
    for (first, fwd_a), (second, fwd_b) in edges.values():
        graph[first].append((second, fwd_a == fwd_b))
        graph[second].append((first, fwd_a == fwd_b))
    flips, shells = {}, []
    for seed in range(len(faces)):
        if seed in flips:
            continue
        flips[seed], pending, indices = False, [seed], []
        while pending:
            current = pending.pop()
            indices.append(current)
            for other, xor in graph[current]:
                needed = flips[current] ^ xor
                if other in flips:
                    if flips[other] != needed:
                        return None
                else:
                    flips[other] = needed
                    pending.append(other)
        oriented = [tri[::-1] if flips[i] else tri for i in indices for tri in faces[i]["triangles"]]
        origin = oriented[0][0]
        volume = abs(math.fsum(_dot(_sub(a, origin), _cross(_sub(b, origin), _sub(c, origin))) / 6
                               for a, b, c in oriented))
        if volume <= 1e-12:
            return None
        shells.append((oriented, volume))
    total = math.fsum(volume * (-1 if sum(_inside(triangles[0][0], other)
                                         for other, _ in shells if other is not triangles) % 2 else 1)
                      for triangles, volume in shells)
    return total if total > 1e-12 else None


def rounded(value, digits):
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def zone_report(reports, components):
    volumes = defaultdict(float)
    for item in components:
        if item["report_visible"]:
            volumes[item["report_zone"].strip() or "(bez názvu)"] += item["raw_volume"]
    names = set(reports["envelope"]) | volumes.keys()
    numbers = build_zone_numbers(names)
    result = []
    for name in names:
        area = rounded(reports["envelope"].get(name, 0), 2)
        ab = rounded(reports["ab"].get(name, 0), 2)
        volume = rounded(volumes[name], 3)
        if name == "(model)" and volume == 0 and area == 0:
            continue
        # Source's m2 already excludes AB; still subtract AB again here,
        # exactly as get_zone_report_table does. Do not silently redefine it.
        result.append({"zone": name, "zoneNumber": str(numbers[name]), "m3": volume,
                       "m2": area, "m2ab": ab, "m2net": rounded(area - ab, 2)})
    return sorted(result, key=lambda row: (int(row["zoneNumber"]), row["zone"]))


def component_palette(reports, components):
    table = {row["zone"]: row for row in zone_report(reports, components)}
    numbers = build_zone_numbers(c["zone"] for c in components)
    result = []
    for component in components:
        if component["zone"] == "(model)" and component["volume"] == 0:
            continue
        row = table.get(component["zone"], {})
        result.append({**component, "zoneNum": str(numbers[component["zone"]]),
                       **{key: row.get(key, 0.) for key in ("m2", "m2ab", "m2net")}})
    return sorted(result, key=lambda item: (int(item["zoneNum"]), item["name"].casefold()))


def report_text(rows):
    header = "Číslo zóny\tZóna\tObjem [m³]\tObálka [m²]\tAB [m²]\tPo odpočtu AB [m²]"
    lines = [header]
    for row in rows:
        lines.append("\t".join([row["zoneNumber"], row["zone"], f"{row['m3']:.3f}",
                                f"{row['m2']:.2f}", f"{row['m2ab']:.2f}", f"{row['m2net']:.2f}"]))
    return "\n".join(lines)
