# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Material naming, validation and the original JSON library (no host/Qt)."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from .core import parse_material_name
from .exports import RP_CATALOG, RP_FIELDS

TYPES = [
    ("SO", "Stěna vnější"), ("SOZ", "Stěna k zemině"),
    ("SCHS", "Střecha strmá"), ("SCH", "Střecha plochá"),
    ("STRV", "Strop nad venkovním"), ("STR", "Strop pod nevytápěným"),
    ("PDL", "Podlaha k zemině"), ("PDLE", "Podlaha nad průlezným"),
    ("OD", "Okno vnější"), ("OS", "Okno střešní"), ("DO", "Dveře vnější"),
    ("DN", "Dveře vnitřní"), ("SNN", "Stěna k podstřeší"),
    ("SN", "Stěna k nevytápěnému"), ("SNG", "Stěna k garáži"),
    ("SNM", "Stěna mezi budovami"), ("STRT", "Strop ΔT≤10 °C"),
    ("SNT", "Stěna ΔT≤10 °C"), ("STR5", "Strop ΔT≤5 °C"),
    ("SNT5", "Stěna ΔT≤5 °C"), ("ODN", "Okno k nevytápěnému"),
    ("ODZ", "Okno do garáže"), ("AB", "Adiabatická hranice"),
    ("EP", "EP (report)"), ("CV", "CV (report)"),
]
WINDOW_TYPES = {"OD", "OS", "ODN", "ODZ"}
RECOMMENDED_COLORS = json.loads(Path(__file__).with_name("recommended_colors.json").read_text(encoding="utf-8"))
RP_CHOICES = {
    "kategorie": ["", *RP_CATALOG["categories"]],
    "typ": ["", *(s for values in RP_CATALOG["categories"].values() for s in values)],
    "etapa": ["", "1. Etapa", "2. Etapa", "3. Etapa"],
    "klient": ["", "Ano", "Ne"], "lze_zateplit": ["Ano", "Ne"],
}


def material_key(name):
    # Independent identity check also recognizes source form's STR5/SNT5.
    # The legacy calculation/export parser remains unchanged.
    match = re.match(r"^([A-Z][A-Z0-9]*)-(\d+)(?:-(V\d+))?(?:-|$)", name, re.I)
    return (match[1].upper(), str(int(match[2])), (match[3] or "V1").upper()) if match else None


def next_free_number(names, typ):
    used = {int(key[1]) for name in names if (key := material_key(name)) and key[0] == typ}
    return next(n for n in range(1, len(used) + 2) if n not in used)


def build_name(data):
    typ = str(data.get("typ", "")).strip().upper()
    number = str(data.get("cislo", "")).strip()
    variant = str(data.get("var", "V1")).strip().upper() or "V1"
    raw_desc = str(data.get("popis", ""))
    desc = raw_desc.strip()
    if typ not in dict(TYPES):
        raise ValueError("Vyberte typ konstrukce.")
    if not re.fullmatch(r"[1-9]\d*", number):
        raise ValueError("Číslo musí být kladné celé číslo.")
    if not re.fullmatch(r"V[1-9]\d*", variant):
        raise ValueError("Varianta musí mít tvar V1, V2, …")
    if any(c in raw_desc for c in "\r\n\x00"):
        raise ValueError("Popis konstrukce nesmí obsahovat zalomení řádků.")
    parts = [typ, number]
    if typ not in {"AB", "EP", "CV"}:
        parts.append(variant)
        for field, prefix in (("u", "U"), ("g", "G")):
            value = str(data.get(field, "")).strip().replace(",", ".")
            if field == "g" and typ not in WINDOW_TYPES:
                continue
            if value:
                if not re.fullmatch(r"\d+(?:\.\d+)?", value) or not math.isfinite(float(value)):
                    raise ValueError(f"{prefix} musí být nezáporné konečné číslo, nebo prázdné.")
                if field == "g" and float(value) > 1:
                    raise ValueError("g musí být v rozsahu 0 až 1.")
                parts.append(prefix + value)
        glazing = str(data.get("sklo", "")).upper()
        if glazing in {"S2", "S3"} and typ in WINDOW_TYPES:
            parts.append(glazing)
    if typ in {"EP", "CV"}:
        parts.append(desc or f"zona {number}")
    elif desc:
        parts.append(desc)
    return "-".join(parts)


def validate_identity(names, new_name, old_name=None):
    if new_name in names and new_name != old_name:
        raise ValueError(f"Materiál už existuje: {new_name}")
    key = material_key(new_name)
    for name in names:
        if name != old_name and name != new_name and material_key(name) == key:
            raise ValueError(f"Stejný typ–číslo–variantu už používá {name}. Zvolte jiné číslo.")


def validate_rp(data):
    result = {}
    for field in RP_FIELDS:
        value = str(data.get(field, "Ano" if field == "lze_zateplit" else ""))
        if value not in RP_CHOICES[field]:
            raise ValueError(f"Neplatná hodnota Renovačního pasu: {field}.")
        result[field] = value
    category, typ = result["kategorie"], result["typ"]
    if typ and (not category or typ not in RP_CATALOG["categories"][category]):
        raise ValueError("Typ Renovačního pasu nepatří do vybrané kategorie.")
    return result


def hex_rgb(value):
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError("Barva musí mít tvar #RRGGBB.")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))


def library_json(materials):
    """The Ruby library is an array; it deliberately carries no RP/texture."""
    result = []
    for name, color in materials:
        p = parse_material_name(name)
        if not p["typ"] or name == "Default":
            continue
        result.append({"name": name, "color": list(color),
                       **{key: p[key] for key in ("typ", "cislo", "var", "u", "g", "popis")}})
    return json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")


def read_library(content):
    """Validate the complete batch before the host begins a mutation."""
    items = json.loads(content)
    if not isinstance(items, list):
        raise ValueError("Knihovna musí obsahovat seznam materiálů.")
    result = []
    names = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Neplatná položka knihovny.")
        name = item.get("name", "")
        if not name:
            continue
        if not isinstance(name, str) or any(c in name for c in "\r\n\x00"):
            raise ValueError("Neplatný název materiálu v knihovně.")
        if name in names:
            raise ValueError(f"Duplicitní materiál v knihovně: {name}")
        names.add(name)
        color = item.get("color")
        if color is None:
            color = [158, 158, 158]
        if (not isinstance(color, list) or len(color) != 3 or
                any(isinstance(c, bool) or not isinstance(c, (int, float)) or
                    not math.isfinite(c) or not 0 <= c <= 255 for c in color)):
            raise ValueError(f"Neplatná RGB barva: {name}")
        result.append((name, tuple(int(c) / 255 for c in color)))
    return result
