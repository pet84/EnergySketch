# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""The three Ruby-compatible CSV serializers, with no GUI dependencies.

RP intentionally uses LOCAL geometry and includes hidden faces, as explicitly
chosen by Petr on 18 October 2026. The schema and historical rounding stay.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import re

from .core import (
    EXPORT_INDICES, HEADERS, aggregate_rows, build_zone_numbers,
    orientation_from_normal, triangulated_area,face_area_m2,
)
from .legacy_sort import ruby_sort_by

RP_CATALOG = json.loads(Path(__file__).with_name("rp_catalog.json").read_text(encoding="utf-8"))
RP_FIELDS = ("kategorie", "typ", "etapa", "klient", "lze_zateplit")
RP_HEADERS = "kategorie,nazev,typ,U,plocha,S,J,V,Z,SV,SZ,JV,JZ,etapa,klient,lze_zateplit"
RP_DIRECTIONS = ("S", "J", "V", "Z", "SV", "SZ", "JV", "JZ")
ENERGY_HEADERS = [
    "Název", "Plocha", "Šířka", "Výška", "Orientace", "Sklon", "U", "g",
    "Kor. činitel zasklení", "Požadavek U.N,20", "Kód konstrukce", "Typ Energie",
    "Číslo zóny", "Zóna", "Činitel tepl. redukce b", "Činitel stínění okolím",
    "Činitel stínění markýzami", "Činitel stínění stěnami", "Činitel clonění žaluziemi",
    "Činitel viditelnosti oblohy",
]
WINDOW_TYPES = {"OD", "OS", "ODN", "ODZ"}
OPENING_TYPES = WINDOW_TYPES | {"DO", "DN"}
FLOOR_TYPES = {"PDL", "PDLE", "SOZ"}
UNHEATED_TYPES = {"SN", "SNN", "SNG", "SNM", "STR", "STRT", "SNT", "STR5", "SNT5"}


def _string(value):
    return "" if value is None else str(value)


def _decimal_comma(value):
    value = _string(value).replace(";", ",")
    return value.replace(".", ",") if re.fullmatch(r"\d+\.\d+", value) else value


def complex_csv(rows):
    lines = [";".join(HEADERS[:-1])]
    lines.extend(";".join(_decimal_comma(row[i]) for i in EXPORT_INDICES)
                 for row in aggregate_rows(rows))
    return ("\ufeff" + "\r\n".join(lines) + "\r\n").encode("utf-8")


def _ruby_float(value):
    # Ruby String#to_f consumes a numeric prefix and returns zero otherwise.
    match = re.match(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)", _string(value))
    return float(match[1]) if match else 0.0


def energy_rows(rows):
    numbers = build_zone_numbers(_string(row[14]) for row in rows)
    groups = {}
    for row in rows:
        typ = _string(row[2])
        if typ == "AB":
            continue
        orient = _string(row[11]).strip()
        if orient in ("N", "H"):
            orient = "H"
        slope = _string(row[12])
        zone = _string(row[14]).strip()
        name = _string(row[13]).strip()
        if not name:
            parts = [_string(row[i]).strip() for i in (2, 3, 4)]
            parts += ["U" + _string(row[5]).strip()] if _string(row[5]).strip() else []
            parts += ["G" + _string(row[6]).strip()] if _string(row[6]).strip() else []
            parts += [_string(row[7]).strip(), _string(row[9]).strip()]
            name = "-".join(part for part in parts if part)
        if not name:
            continue
        key = tuple([zone, typ, *(_string(row[i]) for i in (3, 4, 5, 6, 7, 8)), orient, slope, name])
        area = _ruby_float(row[10])
        window = typ in WINDOW_TYPES
        if key in groups:
            current = groups[key]
            current["Plocha"] = f"{float(current['Plocha']) + area:.2f}"
            if window:
                current["Šířka"] = f"{float(current['Šířka']) + area:.2f}"
        else:
            u = _string(row[5]).strip()
            if not u or _ruby_float(u.replace(",", ".")) <= 0:
                u = "999"
            code = "O" if typ in OPENING_TYPES else "P" if typ in FLOOR_TYPES else "N" if typ in UNHEATED_TYPES else "S"
            groups[key] = {
                "Název": name, "Plocha": f"{area:.2f}",
                "Šířka": f"{area:.2f}" if window else "", "Výška": "1" if window else "",
                "Orientace": orient, "Sklon": slope, "U": u,
                "g": _string(row[6]) if window else "",
                "Kor. činitel zasklení": "0.75" if window else "",
                "Požadavek U.N,20": _string(row[8]), "Kód konstrukce": typ,
                "Typ Energie": code, "Číslo zóny": _string(numbers[zone]), "Zóna": zone,
            }
    return ruby_sort_by(groups.values(), key=lambda r: tuple(r[k] for k in ("Číslo zóny", "Kód konstrukce", "Název", "Orientace")))


def energy_csv(rows):
    lines = [";".join(ENERGY_HEADERS)]
    lines.extend(";".join(_decimal_comma(row.get(key, "")) for key in ENERGY_HEADERS)
                 for row in energy_rows(rows))
    return ("\ufeff" + "\r\n".join(lines) + "\r\n").encode("utf-8")


def detect_rp(name):
    if not name:
        return None
    head = re.split("[-_]", name, maxsplit=1)[0].upper()
    if head in RP_CATALOG["types"]:
        return RP_CATALOG["types"][head]
    for prefix, category, typ in RP_CATALOG["prefixes"]:
        bare = prefix.removesuffix("_")
        if name.startswith(prefix) or name.startswith(bare + "-") or name == bare:
            return [category, typ]
    return None


def read_rp(name, attrs=None):
    attrs = attrs or {}
    result = {field: _string(attrs.get(field, "Ano" if field == "lze_zateplit" else "")) for field in RP_FIELDS}
    if not result["kategorie"] and not result["typ"]:
        detected = detect_rp(name)
        if detected:
            result["kategorie"], result["typ"] = detected
    result["lze_zateplit"] = result["lze_zateplit"] or "Ano"
    return result


def _rp_escape(value):
    value = _string(value)
    if any(c in value for c in (",", '"', "\n")):
        return '"' + value.replace('"', '""') + '"'
    return value


def _rp_number(value):
    # Float#round(2).to_s retains a single .0 for whole numbers.
    return str(float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))


def renovacni_pas_csv(faces, north_angle, material_attrs=None):
    """Exact legacy policy: local area/normal, hidden faces INCLUDED.

    No main-table EP/CV exclusion is applied here: Ruby's RP export considers
    only the FRONT material and its explicitly stored/detected RP attributes.
    """
    material_attrs = material_attrs or {}
    groups = {}
    for face in faces:
        name = face.material
        if not name:
            continue
        attrs = read_rp(name, material_attrs.get(name, {}))
        if not attrs["kategorie"] or not attrs["typ"]:
            continue
        if name not in groups:
            match = re.search(r"-U([\d.]+)", name, re.I)
            groups[name] = {
                **attrs, "nazev": name, "u": _ruby_float(match[1]) if match else 0.0,
                "plocha": 0.0, **{direction: 0.0 for direction in RP_DIRECTIONS},
            }
        row = groups[name]
        area = face_area_m2(face,local=True)
        row["plocha"] += area
        if attrs["kategorie"] == "otvoroveVyplne":
            direction = orientation_from_normal(face.local_normal if face.local_normal is not None else face.normal, north_angle)
            if direction != "H":
                row[direction] += area
    lines = [RP_HEADERS]
    for row in groups.values():
        values = [_rp_escape(row[key]) for key in ("kategorie", "nazev", "typ")]
        values += [_rp_number(row["u"]), _rp_number(row["plocha"])]
        values += [_rp_number(row[d]) if abs(row[d]) >= .001 else "" for d in RP_DIRECTIONS]
        values += [_rp_escape(row[key]) for key in ("etapa", "klient", "lze_zateplit")]
        lines.append(",".join(values))
    return ("\n".join(lines) + "\n").encode("utf-8")
