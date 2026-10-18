# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
from dataclasses import replace
import math

import pytest

from plugins.archcontrol.core import (
    FaceRecord, UN_VALUES, aggregate_rows, build_zone_numbers, collect_rows,
    orientation_from_normal, parse_material_name, slope_from_normal,
    triangulated_area,
)


@pytest.mark.parametrize("name,expected", [
    ("OD-1-V2-U0,9-G0,52-S3-Okno obývák", dict(typ="OD", cislo="1", var="V2", u="0.9", g="0.52", sklo="S3", popis="Okno obývák", un=1.5)),
    ("OS-1", dict(typ="OS", cislo="1", var="V1", u="", g="0.63", sklo="", popis="", un=1.5)),
    ("SO-12-U0.3-Stěna-vnější", dict(typ="SO", cislo="12", var="V1", u="0.3", g="", sklo="", popis="Stěna-vnější", un=0.3)),
    ("Vlastní materiál", dict(typ="", cislo="", var="V1", u="", g="", sklo="", popis="Vlastní materiál", un="")),
])
def test_material_parser(name, expected):
    assert parse_material_name(name) == expected


def test_legacy_parser_numeric_type_defect_is_explicit():
    assert UN_VALUES["STR5"] == 2.2
    assert parse_material_name("STR5-1-U0.4")["typ"] == ""


@pytest.mark.parametrize("degrees,direction", [
    (0, "S"), (22.5, "SV"), (45, "SV"), (67.5, "V"), (90, "V"),
    (112.5, "JV"), (157.5, "J"), (202.5, "JZ"), (247.5, "Z"),
    (292.5, "SZ"), (337.5, "S"),
])
def test_compass_boundaries(degrees, direction):
    # A trig round trip at exactly 202.5 can yield 202.49999999999997 in
    # both runtimes. Check either side explicitly instead of inventing an
    # angular epsilon that would change Ruby's classification semantics.
    angle = degrees + 1e-8
    n = (math.sin(math.radians(angle)), math.cos(math.radians(angle)), 0)
    assert orientation_from_normal(n, 0) == direction
    if degrees % 45 == 22.5:
        from plugins.archcontrol.core import DIRECTIONS
        below = degrees - 1e-8
        n = (math.sin(math.radians(below)), math.cos(math.radians(below)), 0)
        assert orientation_from_normal(n, 0) == DIRECTIONS[(DIRECTIONS.index(direction) - 1) % 8]


def test_rotation_and_north_cancel():
    # Model rotated CCW 90°, NorthAngle also CCW 90°.
    assert orientation_from_normal((-1, 0, 0), 90) == "S"
    assert orientation_from_normal((0, 0, -2), 41) == "H"
    assert slope_from_normal((0, 0, -2)) == 0
    assert slope_from_normal((1, 0, 0)) == 90
    with pytest.raises(ValueError, match="sever"):
        orientation_from_normal((1, 0, 0), None)
    with pytest.raises(ValueError, match="Normála"):
        slope_from_normal((0, 0, 0))


def test_area_handles_nonuniformly_scaled_triangles():
    triangles = (((0, 0, 0), (2, 0, 0), (2, 3, 0)),
                 ((0, 0, 0), (2, 3, 0), (0, 3, 0)))
    assert triangulated_area(triangles) == 6


def record(material="SO-1", **kwargs):
    return FaceRecord("1", (((0, 0, 0), (2, 0, 0), (0, 1, 0)),),
                      (0, 1, 0), material, **kwargs)


def test_ep_cv_back_side_ab_and_missing_material():
    faces = [record(back_material="EP-1"),
             record("CV-1", back_material="EP-1"),
             record("AB-1"), record(""),
             record("SO-2", visible=False), record("SO-3")]
    result = collect_rows(faces, 0)
    assert result["reports"]["ep"] == {"(model)": 2}
    assert result["reports"]["cv"] == {"(model)": 1}
    assert result["reports"]["envelope"] == {"(model)": 1}
    assert result["reports"]["ab"] == {"(model)": 1}
    assert result["no_material_area"] == 1
    assert {row[2] for row in result["rows"]} == {"AB", "SO"}


def test_aggregation_sums_per_face_rounded_areas_and_keeps_ids():
    first = record()
    second = replace(first, pid="2")
    rows = collect_rows([first, second], 0)["rows"]
    rows[0][10] = "1.01"
    rows[1][10] = "1.01"
    result = aggregate_rows(rows)
    assert len(result) == 1
    assert result[0][10] == "2.02"
    assert result[0][16] == "1|2"
    assert rows[0][16] == "1"  # no mutation of input
    rows[1][14] = "Jiná zóna"
    assert len(aggregate_rows(rows)) == 2


def test_zone_number_collision_and_reserved_numbers():
    assert build_zone_numbers(["Zóna 2", "A 2", "Dům", "Zóna 10", "", "Dům"]) == {
        "": "", "A 2": 2, "Zóna 10": 10, "Dům": 1, "Zóna 2": 3}
