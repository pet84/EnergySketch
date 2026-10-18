# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Compare imported triangle areas with an independent polygon JSON oracle.

Input is the read-only C API helper's JSON (units=mm), NOT proprietary parser
internals. The DLL is never bundled or required by the ArchControl plugin.
This verifies area sums by material/visibility, not north or CSV parity.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def polygon_area_mm2(ring):
    normal = [0.0, 0.0, 0.0]
    for a, b in zip(ring, ring[1:] + ring[:1]):
        normal[0] += (a[1]-b[1]) * (a[2]+b[2])
        normal[1] += (a[2]-b[2]) * (a[0]+b[0])
        normal[2] += (a[0]-b[0]) * (a[1]+b[1])
    return math.sqrt(sum(v*v for v in normal)) / 2


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", type=Path)
    ap.add_argument("oracle", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
    source_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
    if oracle.get("sha256") != source_hash or oracle.get("units") != "mm":
        raise ValueError("Referenční geometrie neodpovídá souboru nebo nemá jednotky mm")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication([])
    from plugins.archcontrol.adapter import parse_skp, face_records
    from plugins.archcontrol.core import triangulated_area
    records = list(face_records(parse_skp(args.model)))
    actual, expected = defaultdict(float), defaultdict(float)
    for face in records:
        actual[(face.material, not face.visible)] += triangulated_area(face.triangles)
    for face in oracle["faces"]:
        key = (face["material"]["name"] if face["material"] else "", face["hidden"])
        rings = face["rings"]
        expected[key] += (polygon_area_mm2(rings[0]) - sum(polygon_area_mm2(r) for r in rings[1:])) / 1e6
    rows = [{"material": key[0], "hidden": key[1], "actual": actual[key],
             "oracle": expected[key], "delta_m2": actual[key]-expected[key]}
            for key in sorted(actual.keys() | expected.keys())]
    error = max((abs(row["delta_m2"]) for row in rows), default=0)
    report = {"oracle": "installed C API black-box polygons; independent Newell formula",
              "source_sha256": source_hash, "face_count": len(records),
              "oracle_face_count": len(oracle["faces"]), "rows": rows,
              "max_absolute_area_error_m2": error,
              "source_unchanged": source_hash == hashlib.sha256(args.model.read_bytes()).hexdigest(),
              "ok": len(records) == len(oracle["faces"]) and error <= .01}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"geometry: {report['ok']}; faces={len(records)}; max area error={error:.9f} m2")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
