# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Read a real SKP, generate CSV and compare references without editing inputs.

Use imported shadow north, or explicitly override it for a diagnostic.
An overridden north is not evidence that north was imported.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def compare(actual, reference, delimiter, key_columns, area_columns):
    def rows(data):
        return list(csv.reader(io.StringIO(data.decode("utf-8-sig")), delimiter=delimiter))
    a, b = rows(actual), rows(reference)
    differences = []
    if a[0] != b[0]:
        differences.append({"kind": "header", "actual": a[0], "expected": b[0]})
        return {"ok": False, "differences": differences}
    for label, table in (("actual", a), ("expected", b)):
        for i, row in enumerate(table[1:], 2):
            if len(row) != len(table[0]):
                differences.append({"kind": "row_width", "table": label,
                                    "row": i, "columns": len(row), "required": len(table[0])})
    if differences:
        return {"ok": False, "differences": differences}
    def index(table):
        result = {}
        for row in table[1:]:
            key = tuple(row[i] for i in key_columns)
            if key in result:
                raise ValueError(f"Duplicitní porovnávací klíč: {key}")
            result[key] = row
        return result
    am, bm = index(a), index(b)
    for key in sorted(am.keys() - bm.keys()):
        differences.append({"kind": "extra_row", "key": key, "actual": am[key]})
    for key in sorted(bm.keys() - am.keys()):
        differences.append({"kind": "missing_row", "key": key, "expected": bm[key]})
    for key in sorted(am.keys() & bm.keys()):
        ar, br = am[key], bm[key]
        for i, (av, bv) in enumerate(zip(ar, br)):
            if av == bv:
                continue
            if i in area_columns and av and bv:
                delta = float(av.replace(",", ".")) - float(bv.replace(",", "."))
                if abs(delta) <= .01 + 1e-10:
                    continue
            differences.append({"kind": "cell", "key": key, "column": a[0][i], "actual": av, "expected": bv})
    order_matches = [tuple(r[i] for i in key_columns) for r in a[1:]] == [tuple(r[i] for i in key_columns) for r in b[1:]]
    return {"ok": not differences and order_matches, "actual_rows": len(a)-1,
            "reference_rows": len(b)-1, "row_order_matches": order_matches,
            "differences": differences, "byte_identical": actual == reference}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", type=Path)
    ap.add_argument("--north", type=float)
    ap.add_argument("--energy", type=Path)
    ap.add_argument("--rp", type=Path)
    ap.add_argument("--complex", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--igz-roundtrip", action="store_true",
                    help="Save an isolated IGZ and compare exports from its reopened scene.")
    args = ap.parse_args()
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    from plugins.archcontrol.adapter import face_records, parse_skp
    from plugins.archcontrol.core import collect_rows
    from plugins.archcontrol.exports import complex_csv, energy_csv, renovacni_pas_csv
    before = hashlib.sha256(args.model.read_bytes()).hexdigest()
    scene = parse_skp(args.model)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.igz_roundtrip:
        from core.scene import Scene
        from formats.igz import save_scene, load_into
        igz = args.output / "roundtrip.igz"
        save_scene(scene, igz)
        scene = Scene()
        load_into(scene, igz)
    imported_north = scene.plugin_data["archcontrol"].get("north_angle")
    north = imported_north if args.north is None else args.north
    if north is None:
        raise ValueError("Importér sever tohoto formátu nezná; pro diagnostiku výslovně zadejte --north.")
    faces = list(face_records(scene))
    collected = collect_rows(faces, north)
    dictionaries = scene.plugin_data["archcontrol"].get("material_dictionaries", {})
    rp_attrs = {name: ds.get("ArchControl_RP", {}) for name, ds in dictionaries.items()}
    outputs = {
        "complex": complex_csv(collected["rows"]),
        "energy": energy_csv(collected["rows"]),
        "rp": renovacni_pas_csv(faces, north, rp_attrs),
    }
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"model": str(args.model), "source_sha256": before,
              "igz_roundtrip": args.igz_roundtrip,
              "north_supplied_for_diagnostic": args.north, "north_import_verified": args.north is None and imported_north is not None,
              "north_used":north,
              "face_count": len(faces), "material_names": sorted(scene.materials),
              "comparisons": {}}
    for key, data in outputs.items():
        (args.output / f"{key}.csv").write_bytes(data)
        reference_path = getattr(args, key)
        if reference_path:
            reference = reference_path.read_bytes()
            if key == "energy":
                result = compare(data, reference, ";", (0, 4, 5, 13), {1, 2})
            elif key == "rp":
                result = compare(data, reference, ",", (0, 1, 2), set(range(4, 13)))
            else:
                result = compare(data, reference, ";", tuple(i for i in range(14) if i != 9), {9})
            result["reference_path"] = str(reference_path)
            result["reference_sha256"] = hashlib.sha256(reference).hexdigest()
            report["comparisons"][key] = result
        else:
            report["comparisons"][key] = {"ok": None, "reason": "reference_not_supplied"}
    report["source_unchanged"] = before == hashlib.sha256(args.model.read_bytes()).hexdigest()
    (args.output / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    for key, result in report["comparisons"].items():
        print(f"{key}: {result['ok']}, differences={len(result.get('differences', []))}")
    return int(any(r["ok"] is False for r in report["comparisons"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
