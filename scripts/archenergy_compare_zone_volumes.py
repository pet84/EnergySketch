# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Compare zone volumes against independent read-only SDK polygon evidence.

Uses a polygon divergence sum, not the host's triangle tetrahedra. The SDK
is not loaded here or required by EnergySketch. Only direct root instances
with unit scale are compared: nested/local volume rules need separate data.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plugins.archcontrol.adapter import parse_skp, component_records


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def polygon_volume(faces):
    edges, total = Counter(), 0.
    for face in faces:
        outer = None
        for ring in face["rings"]:
            vector = [0., 0., 0.]
            for a, b in zip(ring, [*ring[1:], ring[0]]):
                for i, value in enumerate(cross(a, b)):
                    vector[i] += value / 2
                ka, kb = (tuple(round(v, 5) for v in p) for p in (a, b))
                edges[tuple(sorted((ka, kb)))] += 1
            if outer is None:
                outer = vector
            elif dot(vector, outer) > 0:
                vector = [-v for v in vector]
            total += dot(ring[0], vector) / 3
    closed = bool(edges) and all(value == 2 for value in edges.values())
    return (abs(total) / 1e9 if closed else None), closed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("oracle", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sdk-oracle", type=Path)
    args = parser.parse_args()
    oracle = json.loads(args.oracle.read_text(encoding="utf-8"))
    digest = hashlib.sha256(args.model.read_bytes()).hexdigest()
    if oracle["sha256"] != digest or oracle["units"] != "mm":
        raise ValueError("Kontrolní geometrie není stejného modelu v mm.")
    faces = defaultdict(list)
    for face in oracle["faces"]:
        faces[face["path"]].append(face)
    native = {row["name"]: row for row in component_records(parse_skp(args.model))}
    comparisons = []
    for group in oracle["groups"]:
        if group["path"] != "root" or group["kind"] != "instance":
            raise ValueError("Tento audit vyžaduje přímé kořenové komponenty.")
        matrix = group["transform"]
        if any(abs(matrix[i] - expected) > 1e-9 for i, expected in
               ((0, 1), (1, 0), (2, 0), (4, 0), (5, 1), (6, 0), (8, 0), (9, 0), (10, 1))):
            raise ValueError("Audit kořenové transformace podporuje pouze posun.")
        volume, closed = polygon_volume(faces["root/" + group["name"]])
        row = native[group["name"]]
        difference = abs(volume - row["raw_volume"]) if volume is not None else None
        comparisons.append({"name": group["name"], "oracle_closed": closed,
                            "native_solid": row["solid"], "oracle_volume_m3": volume,
                            "native_volume_m3": row["raw_volume"], "difference_m3": difference,
                            "ok": closed == row["solid"] and (difference is None or difference <= .001)})
    result = {"ok": bool(comparisons) and all(row["ok"] for row in comparisons),
              "source_sha256": digest, "tolerance_m3": .001, "comparisons": comparisons}
    if args.sdk_oracle:
        sdk = json.loads(args.sdk_oracle.read_text(encoding="utf-8"))
        if sdk["source_sha256"] != digest:
            raise ValueError("SDK kontrola nepatří ke stejnému souboru.")
        checks = []
        for entry in sdk["values"]:
            measured = native[entry["name"]]
            expected = entry["volume_m3"]
            difference = abs(measured["raw_volume"] - expected) if expected is not None else None
            checks.append({"name": entry["name"], "sdk_status": entry["status"],
                           "difference_m3": difference,
                           "ok": measured["solid"] == (entry["status"] == 0) and
                                  (difference is None or difference <= .001)})
        result["sdk_comparisons"] = checks
        result["ok"] = result["ok"] and bool(checks) and all(row["ok"] for row in checks)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
