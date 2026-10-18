# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
import csv
import io
from dataclasses import replace

from plugins.archcontrol.core import FaceRecord, collect_rows
from plugins.archcontrol.exports import (
    complex_csv, energy_csv, read_rp, renovacni_pas_csv,
)

TRIANGLES = (((0, 0, 0), (2, 0, 0), (0, 1, 0)),)


def face(material="OD-1-U0.9-G0.5-S3-Okno", **kw):
    return FaceRecord("source-1", TRIANGLES, (0, 1, 0), material,
                      zone="Zóna 2", parent_name="Zóna 2", **kw)


def parse(data, delimiter):
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=delimiter))


def test_complex_csv_exact_bytes_rounding_and_decimal_comma():
    a = face("SO-1-U0.3-Popis;část", color="#112233")
    rows = collect_rows([a, replace(a, pid="source-2")], 0)["rows"]
    data = complex_csv(rows)
    expected = (
        "\ufeffHladina;Typ;Číslo;Var;U;g;Sklo;Un;Popis;Plocha [m²];Orientace;Sklon;Zóna;Barva\r\n"
        "Layer0;SO;1;V1;0,3;;;0,3;Popis,část;2,00;S;90,0;Zóna 2;#112233\r\n"
    ).encode("utf-8")
    assert data == expected
    assert len(parse(data, ";")[1]) == 14


def test_energy_has_20_columns_and_correct_zone_window_fields():
    rows = collect_rows([face(), face("AB-1"), face("SO-1")], 0)["rows"]
    data = energy_csv(rows)
    assert data.startswith(b"\xef\xbb\xbf")
    table = parse(data, ";")
    assert len(table) == 3
    assert all(len(row) == 20 for row in table)
    assert table[1] == ["OD-1-U0.9-G0.5-S3-Okno", "1,00", "1,00", "1", "S", "90,0",
                        "0,9", "0,5", "0,75", "1,5", "OD", "O", "2", "Zóna 2", "", "", "", "", "", ""]
    assert table[2][6] == "999"  # Ruby's unknown-U sentinel
    assert table[2][11] == "S"


def test_energy_zone_order_is_historical_lexical_order():
    faces = [replace(face(), zone="Zóna 2", parent_name="Zóna 2"),
             replace(face(), zone="Zóna 10", parent_name="Zóna 10")]
    table = parse(energy_csv(collect_rows(faces, 0)["rows"]), ";")
    assert [row[12] for row in table[1:]] == ["10", "2"]


def test_rp_keeps_local_geometry_and_hidden_faces_by_explicit_choice():
    f = face()
    f = replace(f, visible=False,
                triangles=(((0, 0, 0), (4, 0, 0), (0, 1, 0)),),
                normal=(1, 0, 0), local_triangles=TRIANGLES, local_normal=(0, 1, 0))
    data = renovacni_pas_csv([f], 0)
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in data
    table = parse(data, ",")
    assert len(table[0]) == len(table[1]) == 16
    assert table[1][3:7] == ["0.9", "1.0", "1.0", ""]
    assert table[1][7] == ""  # world-facing E is intentionally ignored
    assert table[1][15] == "Ano"


def test_rp_precise_type_text_and_csv_escaping():
    name = 'SCH-2-U0.12-Střecha, "část"'
    attrs = {name: {"kategorie": "strechy", "typ": "Střecha šikmá se sklonem do 60° včetně",
                    "etapa": "2. Etapa", "klient": "Ne", "lze_zateplit": "Ano"}}
    data = renovacni_pas_csv([face(name)], 0, attrs)
    assert b'"SCH-2-U0.12-' in data
    row = parse(data, ",")[1]
    assert row[1] == name
    assert row[2] == attrs[name]["typ"]
    assert row[-3:] == ["2. Etapa", "Ne", "Ano"]


def test_rp_autofill_only_when_both_category_and_type_are_empty():
    assert read_rp("SOZ-1")["typ"] == "Stěna vytápěného prostoru přilehlá k zemině"
    assert read_rp("SO-1", {"kategorie": "steny"})["typ"] == ""
    assert read_rp("AB-1")["kategorie"] == ""
    assert read_rp("EP-1")["kategorie"] == ""


def test_rp_does_not_apply_main_table_back_report_exclusion():
    f = face("SO-1", back_material="EP-1")
    assert collect_rows([f], 0)["rows"] == []
    assert len(parse(renovacni_pas_csv([f], 0), ",")) == 2


def test_rp_skylight_has_area_but_no_direction():
    data = renovacni_pas_csv([replace(face(), normal=(0, 0, -1))], 0)
    row = parse(data, ",")[1]
    assert row[4] == "1.0"
    assert row[5:13] == [""] * 8
