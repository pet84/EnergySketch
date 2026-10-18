# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Audit raw OpenSKP -> upstream payload -> Scene without editing source models.

This is an import diagnostic, NOT reference CSV validation. Raw parser output
is not an independent oracle. Run from any directory using the project's venv.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def audit(path: Path, adapter="upstream") -> dict:
    import openskp
    from core.scene import Scene
    from formats import openskp_compat
    from formats.skp_openskp import _adapt
    from formats.skp import apply_payload

    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {"path": str(path.resolve()), "sha256": before}
    try:
        openskp_compat.apply()
        if adapter == "archcontrol":
            from plugins.archcontrol.adapter import read_skp
            _reader, model, _metadata = read_skp(path)
        else:
            model = openskp.SkpFile.open(str(path)).parse()
        definitions = model.definitions
        source_names = Counter()
        instances = []
        source_faces = Counter()

        def walk(defn, parents=(), stack=frozenset()):
            if id(defn) in stack:
                raise ValueError("Cyclic definition graph")
            for face in defn.faces.values():
                for side, key in (("front", "material_id"),
                                  ("back", "back_material_id")):
                    material = model.materials_by_id.get(getattr(face, key, None))
                    if material is not None:
                        source_faces[f"{side}:{material.name}"] += 1
            for instance in defn.instances:
                child = definitions.get(instance.ref_idx)
                if child is None:
                    continue
                name = instance.name if instance.name.strip() else child.name
                source_names[name] += 1
                instances.append({
                    "path": list(parents + (name,)),
                    "instance_name": instance.name,
                    "definition_name": child.name,
                    "dictionaries": instance.attribute_dictionaries,
                    "hidden": instance.hidden,
                })
                walk(child, parents + (name,), stack | {id(defn)})

        walk(model.root)
        result["source"] = {
            "version": model.version,
            "material_names": sorted(m.name for m in model.materials),
            "instances": instances,
            "instance_names": dict(source_names),
            "face_material_uses": dict(source_faces),
            "layers": [{"name": ly.name, "hidden": ly.hidden} for ly in model.layers],
            "model_fields": sorted(vars(model)),
        }
        if adapter == "archcontrol":
            from plugins.archcontrol.adapter import parse_skp
            scene = parse_skp(path)
            payload = {}
        else:
            payload = _adapt(model, path.stem, skp_path=path)
            if not payload:
                raise ValueError("Upstream adapter returned no geometry")
            scene = Scene()
            apply_payload(scene, payload)
        scene_names = Counter()
        scene_faces = Counter()

        def walk_group(group):
            scene_names[group.name] += 1
            for face in group.mesh.faces:
                if face.attrs.get("mat"):
                    scene_faces[f"front:{face.attrs['mat']}"] += 1
                back = face.attrs.get("back")
                if back is True:
                    back = face.attrs
                if isinstance(back, dict) and back.get("mat"):
                    scene_faces[f"back:{back['mat']}"] += 1
            for child in group.children:
                walk_group(child)

        for group in scene.groups:
            walk_group(group)
        missing_names = source_names - scene_names
        source_materials = set(result["source"]["material_names"])
        result["imported"] = {
            "payload_fields": sorted(payload),
            "material_names": sorted(scene.materials),
            "group_names": dict(scene_names),
            "face_material_uses": dict(scene_faces),
            "layers": [ly.name for ly in scene.layers],
            "plugin_data": scene.plugin_data,
            "group_extensions": [g.ext for g in scene.groups],
        }
        result["differences"] = {
            "missing_material_names": sorted(source_materials - set(scene.materials)),
            "missing_instance_names_multiset": dict(missing_names),
            "note": "Includes nested containers; name equality alone does not prove zone ownership.",
        }
        result["status"] = "name_loss" if missing_names or result["differences"]["missing_material_names"] else "names_match_only"
    except Exception:
        result["status"] = "error"
        result["error"] = traceback.format_exc()
    finally:
        result["source_unchanged"] = before == hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("models", type=Path, nargs="+")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--adapter", choices=("upstream", "archcontrol"), default="upstream")
    args = ap.parse_args()
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    report = {
        "upstream_commit": subprocess.check_output(
            ["git", "rev-parse", "upstream/main"], cwd=ROOT, text=True).strip(),
        "openskp_version": importlib.metadata.version("openskp"),
        "adapter": args.adapter,
        "independent_reference_validation": False,
        "models": [],
    }
    for path in args.models:
        row = audit(path, args.adapter)
        report["models"].append(row)
        print(f"{path.name}: {row['status']}", flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return int(any(r["status"] != "names_match_only" or not r["source_unchanged"]
                   for r in report["models"]))


if __name__ == "__main__":
    raise SystemExit(main())
