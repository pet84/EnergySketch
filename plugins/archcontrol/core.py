# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Pure Python ArchControl calculations; no Qt or IngeTrazo imports.

The 22-column row layout and aggregation follow arch_control_core.rb.
Keep formatting/rounding BEFORE aggregation: the Ruby table sums rounded
per-face areas, not full precision areas. CSV compatibility relies on this.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from .legacy_sort import ruby_sort_by

UN_VALUES = json.loads(Path(__file__).with_name("un_values.json").read_text(encoding="utf-8"))
WINDOW_TYPES = {"OD", "OS", "OX", "ODN", "ODZ"}
DIRECTIONS = ("S", "SV", "V", "JV", "J", "JZ", "Z", "SZ")
HEADERS = ["Hladina", "Typ", "Číslo", "Var", "U", "g", "Sklo", "Un", "Popis",
           "Plocha [m²]", "Orientace", "Sklon", "Zóna", "Barva", "PID"]
EXPORT_INDICES = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15]


def parse_material_name(name: str) -> dict:
    """Compatibility parser, including the original all-letter TYPE regex.

    Known source defect: STR5/SNT5 have Un entries but Ruby cannot parse
    their names. Do not silently change legacy exports; resolve explicitly.
    """
    result = dict(typ="", cislo="", var="V1", u="", g="", sklo="", popis=name)
    match = re.fullmatch(
        r"([A-Z]+)-(\d+)(?:-(V\d+))?(?:-U([\d.]+))?(?:-G([\d.]+))?"
        r"(?:-(S[23]))?(?:-(.*))?", name.replace(",", "."), re.I)
    if match:
        typ, number, variant, u, g, glazing, description = match.groups()
        result.update(typ=typ.upper(), cislo=number, var=variant or "V1",
                      u=u or "", g=g or "", sklo=(glazing or "").upper(),
                      popis=description or "")
    if result["typ"] in WINDOW_TYPES and not result["g"]:
        result["g"] = "0.63"
    result["un"] = UN_VALUES.get(result["typ"], "")
    return result


def normalized(normal):
    length = math.sqrt(sum(v * v for v in normal))
    if not length or not math.isfinite(length):
        raise ValueError("Normála musí být konečná a nenulová")
    return tuple(v / length for v in normal)


def orientation_from_normal(normal, north_angle):
    if north_angle is None or not math.isfinite(north_angle):
        raise ValueError("Nejprve je nutné doložit nebo nastavit sever modelu")
    x, y, z = normalized(normal)
    if abs(z) >= 0.9:
        return "H"
    azimuth = (math.degrees(math.atan2(x, y)) + north_angle + 360) % 360
    return DIRECTIONS[int((azimuth + 22.5) // 45) % 8]


def north_from_points(first, second):
    """Ruby NorthTool's final formula: CCW from +Y, projected to XY."""
    if any(not math.isfinite(v) for v in (*first, *second)):
        raise ValueError("Body severu musí mít konečné souřadnice.")
    x, y = second[0] - first[0], second[1] - first[1]
    if math.hypot(x, y) < 1e-9:
        raise ValueError("Body musí určit nenulový směr v půdorysu.")
    return math.degrees(math.atan2(-x, y)) % 360


def slope_from_normal(normal):
    z = abs(normalized(normal)[2])
    return math.degrees(math.acos(min(1.0, z)))


def triangle_area(a, b, c):
    u = tuple(b[i] - a[i] for i in range(3))
    v = tuple(c[i] - a[i] for i in range(3))
    cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])
    return math.sqrt(sum(x * x for x in cross)) / 2


def triangulated_area(triangles):
    area = math.fsum(triangle_area(*t) for t in triangles)
    if not math.isfinite(area):
        raise ValueError("Plocha není konečné číslo")
    return area


def build_zone_numbers(names):
    result, used = {"": ""}, set()
    names = sorted({name.strip() for name in names if name.strip()})
    for name in names:
        match = re.search(r"\d+", name)
        if match and int(match[0]) not in used:
            number = int(match[0])
            result[name] = number
            used.add(number)
    next_number = 1
    for name in names:
        if name in result:
            continue
        while next_number in used:
            next_number += 1
        result[name] = next_number
        used.add(next_number)
    return result


def aggregate_rows(rows):
    groups = {}
    for source in rows:
        key = tuple(str(source[i]) for i in [*range(10), 11, 12, 13, 14])
        if key not in groups:
            groups[key] = [list(source), 0.0, []]
        group = groups[key]
        group[1] += float(source[10])
        group[2].append(str(source[16]))
    result = []
    for row, area, ids in groups.values():
        row[10] = f"{area:.2f}"
        row[16] = "|".join(ids)
        result.append(row)
    return ruby_sort_by(result, key=lambda row: (row[0], row[1]))


@dataclass(frozen=True)
class FaceRecord:
    """Adapter boundary, lengths in metres, triangles already transformed.

    `zone` is the OUTERMOST component (reports); `parent_name` is the face
    definition's name (Ruby table uses this different rule). Original
    entities not classified as groups/components must be flagged by adapter.
    """
    pid: str
    triangles: tuple
    normal: tuple
    material: str = ""
    back_material: str = ""
    layer: str = "Layer0"
    zone: str = "(model)"
    parent_name: str = ""
    color: str = "#9e9e9e"
    rp: tuple = ("", "", "", "", "Ano")
    visible: bool = True
    local_triangles: tuple | None = None
    local_normal: tuple | None = None
    source_triangles_inches: tuple | None = None
    source_local_triangles_inches: tuple | None = None


def face_area_m2(face,local=False):
    """Use live-validated original double coordinates in Ruby's native units.

    Converting to metres before subtracting/crossing can round a half-cent
    differently. Ordinary edited/native faces use their current metre geometry.
    """
    source = face.source_local_triangles_inches if local else face.source_triangles_inches
    if source is not None:
        return triangulated_area(source)*.00064516
    triangles = face.local_triangles if local and face.local_triangles is not None else face.triangles
    return triangulated_area(triangles)


def collect_rows(faces, north_angle, *, include_rows=True):
    rows = []
    reports = {key: defaultdict(float) for key in ("ep", "cv", "envelope", "ab")}
    missing_area, missing_ids = 0.0, []
    for face in faces:
        if not face.visible:
            continue
        area = face_area_m2(face)
        is_ep = any(re.match(r"EP-\d", name, re.I) for name in (face.material, face.back_material))
        is_cv = any(re.match(r"CV-\d", name, re.I) for name in (face.material, face.back_material))
        if is_ep or is_cv:
            if is_ep:
                reports["ep"][face.zone] += area
            if is_cv:
                reports["cv"][face.zone] += area
            continue
        if not face.material.strip() or "default" in face.material.lower():
            missing_area += area
            missing_ids.append(face.pid)
            continue
        p = parse_material_name(face.material)
        reports["ab" if p["typ"] == "AB" else "envelope"][face.zone] += area
        if not include_rows:
            continue
        rows.append([
            face.layer, face.material, p["typ"], p["cislo"], p["var"], p["u"], p["g"],
            p["sklo"], p["un"], p["popis"], f"{area:.2f}",
            orientation_from_normal(face.normal, north_angle),
            f"{slope_from_normal(face.normal):.1f}", face.material,
            face.parent_name, face.color, face.pid, *face.rp,
        ])
    return {
        "rows": ruby_sort_by(rows, key=lambda row: (row[0], row[1])),
        "reports": {key: dict(value) for key, value in reports.items()},
        "no_material_area": missing_area, "no_material_pids": missing_ids,
    }
