# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Private live document for a real Codex/MCP trial, never a customer model.

Run with the repository's Python and an empty evidence directory. ready.json
publishes a random loopback port; finish.request captures and closes ONLY this
process. A 15 minute watchdog closes an abandoned trial. No API credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    out = args.directory.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        parser.error("Evidence directory must be empty; existing files are preserved.")
    os.environ.pop("QT_QPA_PLATFORM", None)
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="energysketch-codex-")
    os.environ["INGETRAZO_AI_PORT"] = "0"
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication
    from core.archenergy import configure_profile
    from core.orient import is_closed
    from core.scene import Scene
    from formats.igz import load_into, save_scene
    from main import _configure_surface_format, _init_language
    from plugins.ai_bridge import _Bridge
    from views.main_window import MainWindow
    from views.theme import apply_theme

    _configure_surface_format()
    app = QApplication([])
    configure_profile()
    _init_language()
    apply_theme(app)
    window = MainWindow(defer_extensions=True)
    window.setAttribute(Qt.WA_ShowWithoutActivating, True)
    window.resize(1400, 950)
    window.move(-32000, -32000)
    vp = window.viewport
    # Start with an explicitly empty private document, with no reference figure.
    from core.history import History
    vp.scene = Scene()
    vp.history = History(vp.scene)
    bridge = _Bridge(vp)
    events = []
    original_run = bridge._tool_run_python

    def measured_run(code=""):
        result = original_run(code)
        events.append({"code": code, **result})
        (out / "executions.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    bridge._tool_run_python = measured_run
    started = time.monotonic()
    report = {"ok": False, "customer_model_opened": False}

    def finish(timeout=False):
        timer.stop()
        try:
            assert not timeout, "Codex demo timed out"
            groups = list(vp.scene.groups)
            assert len(groups) == 4, f"Expected four house groups, got {len(groups)}"
            assert len(events) and not any(e["error"] for e in events)
            changed = [e for e in events if e["changed"]]
            assert len(vp.history.undo_stack) == 1, "House should be a single undo step"
            assert "house(" in changed[-1]["code"], "Native house helper was not used"
            walls, floor, carpentry, roof = groups
            panes = [f for f in carpentry.mesh.faces if f.attrs.get("opacity")]
            assert len(panes) >= 4, "Missing window panes"
            assert any(f.hole_loops for f in walls.mesh.faces), "No wall openings"
            assert all(is_closed(g.mesh) for g in (walls, floor, roof))
            # The floor is inset inside the walls; external size is measured
            # on the walls, rather than mistaking the inset slab for a footprint.
            xs = [v.position.x() for v in walls.mesh.vertices]
            ys = [v.position.y() for v in walls.mesh.vertices]
            assert abs(max(xs)-min(xs)-8) < .00001
            assert abs(max(ys)-min(ys)-6) < .00001
            zs = [v.position.z() for v in roof.mesh.vertices]
            assert max(zs)-min(zs) > 1, "Roof has no pitched ridge"
            pane_bounds = []
            for face in panes:
                points = face.vertices
                pane_bounds.append({
                    "min": [min(getattr(p, axis)() for p in points) for axis in ("x", "y", "z")],
                    "max": [max(getattr(p, axis)() for p in points) for axis in ("x", "y", "z")]})
            assert sum(abs(p["min"][0]-.125) < .00001 for p in pane_bounds) == 2
            assert sum(abs(p["min"][0]-7.875) < .00001 for p in pane_bounds) == 1
            assert sum(abs(p["min"][1]-.125) < .00001 for p in pane_bounds) == 1
            assert all(abs(p["min"][2]-.9) < .00001 and abs(p["max"][2]-2.2) < .00001
                       for p in pane_bounds)
            assert vp.history.undo() and not vp.scene.groups
            assert vp.history.redo() and len(vp.scene.groups) == 4
            vp.notify_scene_changed()
            window._on_zoom_extents()
            app.processEvents()
            image = vp.render_image(1280, 960)
            assert not image.isNull() and image.save(str(out / "dum.png"))
            model = out / "dum.igz"
            save_scene(vp.scene, model)
            reopened = Scene()
            load_into(reopened, model)
            assert len(reopened.groups) == 4
            report.update(ok=True, groups=[g.name for g in vp.scene.groups],
                          group_faces=[len(g.mesh.faces) for g in vp.scene.groups],
                          window_panes=len(panes), window_bounds=pane_bounds,
                          walls_floor_roof_closed=True,
                          width_m=8, depth_m=6, undo_redo=True, igz_roundtrip=True,
                          transaction_seconds=changed[-1]["execution_seconds"],
                          modeling_attempts=len(changed),
                          model=str(model), image=str(out / "dum.png"),
                          model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),
                          gl_info=getattr(vp, "gl_info", {}))
        except Exception:
            import traceback
            report["traceback"] = traceback.format_exc()
        report["host_lifetime_seconds"] = round(time.monotonic()-started, 3)
        (out / "host-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        bridge.stop()
        window._saved_version = vp.scene.version
        window.close()
        app.exit(0 if report["ok"] else 1)

    def ready():
        port = bridge.start()
        (out / "ready.json").write_text(json.dumps(
            {"pid": os.getpid(), "port": port, "initial_groups": 0,
             "private_profile": True}), encoding="utf-8")

    def check():
        if (out / "finish.request").exists():
            finish()
        elif time.monotonic()-started > 900:
            finish(timeout=True)

    timer = QTimer()
    timer.timeout.connect(check)
    timer.start(250)
    window.show()
    QTimer.singleShot(1000, ready)
    app.exec()
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
