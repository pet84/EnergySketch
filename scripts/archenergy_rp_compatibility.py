# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Reproduce the RP contract conflict on a 1 m² vertical square.

This is a mathematical illustration of the read source code, not an export
executed in the original Ruby runtime and not an independent CSV reference.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plugins.archcontrol.core import orientation_from_normal, triangulated_area


def main():
    local = (((0, 0, 0), (1, 0, 0), (1, 0, 1)),
             ((0, 0, 0), (1, 0, 1), (0, 0, 1)))
    # Rotate clockwise 90° about Z, then scale the facade's width by 2.
    def transform(p):
        x, y, z = p
        return (y, -2 * x, z)

    world = tuple(tuple(transform(p) for p in t) for t in local)
    report = {
        "illustration_only_not_executed_in_ruby": True,
        "source": {
            "file": "arch_control/arch_control_renovacni_pas.rb",
            "area_line": 290, "normal_line": 294, "recursion_line": 305,
            "behavior": "face.area and face.normal; path transformations unused; no visibility filtering",
        },
        "fixture": "1 m² facade, front normal +Y; clockwise 90° rotation and 2x width",
        "north_angle_for_fixture": 0,
        "legacy_rp_algorithm": {
            "area_m2": triangulated_area(local),
            "orientation": orientation_from_normal((0, 1, 0), 0),
            "hidden_faces": "included",
        },
        "transformed_algorithm": {
            "area_m2": triangulated_area(world),
            "orientation": orientation_from_normal((1, 0, 0), 0),
            "hidden_faces": "excluded when following the main table",
        },
        "csv_schema_in_both_options": "unchanged, 16 columns",
        "decision": "Petr explicitly chose exact legacy numerical parity: local geometry, hidden faces included",
        "decision_date": "2026-10-18",
    }
    output = Path(__file__).resolve().parents[1] / "output/archenergy/rp-compatibility-decision.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
