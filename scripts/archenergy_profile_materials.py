# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Read-only timing/profile of ArchControl reports for a private model copy."""
import argparse
import cProfile
import hashlib
import io
import json
import os
from pathlib import Path
import pstats
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="energy-material-profile-")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", type=Path)
    ap.add_argument("report", type=Path)
    args = ap.parse_args()
    from PySide6.QtWidgets import QApplication
    from core.archenergy import configure_profile
    from plugins.archcontrol.adapter import PanelService, parse_skp
    app = QApplication([])
    configure_profile()
    before = hashlib.sha256(args.model.read_bytes()).hexdigest()
    started = time.perf_counter()
    scene = parse_skp(args.model)
    report = {"model_sha256": before, "load_seconds": time.perf_counter()-started,
              "materials": len(scene.materials)}
    service = PanelService(SimpleNamespace(scene=scene, window=None,
        document_data=lambda **kw: scene.plugin_data.get("archcontrol", {})))
    for name in ("data", "materials", "zones"):
        started = time.perf_counter()
        result = getattr(service, name)()
        report[name+"_seconds"] = time.perf_counter()-started
        report[name+"_rows"] = len(result["rows"] if isinstance(result, dict) else result)
        print(json.dumps({name: report[name+"_seconds"]}), flush=True)
    profile = cProfile.Profile()
    profile.runcall(service.materials)
    stream = io.StringIO()
    pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(22)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.with_suffix(".txt").write_text(stream.getvalue(), encoding="utf-8")
    report["source_unchanged"] = hashlib.sha256(args.model.read_bytes()).hexdigest() == before
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
