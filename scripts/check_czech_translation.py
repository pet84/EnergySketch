# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Validate Czech keys against the union of all shipped translation catalogs.

Metadata (_comment etc.) is excluded. Missing/empty values, duplicate keys,
placeholder changes and lost/new newlines are errors. This checks structure,
not translation quality. Identical source/target values need human review.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import string


def load_catalog(path):
    duplicates = []

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                duplicates.append(key)
            result[key] = value
        return result

    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: katalog musí být objekt")
    if duplicates:
        raise ValueError(f"{path}: duplicitní klíče: {duplicates[:5]!r}")
    return {key: value for key, value in data.items() if not key.startswith("_")}


def placeholders(text):
    try:
        fields = []
        for _, field, spec, conversion in string.Formatter().parse(text):
            if field is not None:
                fields.append((field, spec, conversion))
        return Counter(fields)
    except ValueError:
        # Some source labels contain literal single braces without .format.
        return Counter(re.findall(r"\{[a-zA-Z_]\w*(?:![rsa])?(?::[^{}]*)?\}", text))


def check(directory, target="cs"):
    required = set()
    errors = []
    for source in sorted(directory.glob("*.json")):
        if source.stem in (target, "en"):
            continue
        required.update(load_catalog(source))
    path = directory / f"{target}.json"
    if not path.is_file():
        return {"ok": False, "required": len(required), "translated": 0,
                "errors": [f"Chybí {path}"]}
    catalog = load_catalog(path)
    for key in sorted(required - catalog.keys()):
        errors.append(f"Chybí klíč: {key}")
    for key, value in catalog.items():
        if not isinstance(value, str) or (key and not value.strip()):
            errors.append(f"Prázdný/neplatný překlad: {key}")
            continue
        if placeholders(key) != placeholders(value):
            errors.append(f"Změněné placeholdery: {key}")
        if key.count("\n") != value.count("\n"):
            errors.append(f"Změněné odřádkování: {key}")
    return {"ok": not errors, "required": len(required), "translated": len(catalog),
            "identical_source_values": sum(k == v for k, v in catalog.items()),
            "errors": errors}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--directory", type=Path,
                    default=Path(__file__).resolve().parents[1] / "i18n")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    try:
        report = check(args.directory)
    except (OSError, ValueError) as exc:
        report = {"ok": False, "errors": [str(exc)]}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
