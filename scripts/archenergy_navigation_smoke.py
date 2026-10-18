# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Measure real navigation/edit-entry with all ArchControl panels loaded.

Always use a private model copy. The own off-desktop OpenGL window and profile
are closed without saving. No customer application or document is controlled.
"""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", type=Path)
    ap.add_argument("report", type=Path)
    ap.add_argument("--materials", action="store_true", help="Keep the material palette visible")
    ap.add_argument("--sample", action="store_true", help="Also test a native eyedropper click on visible geometry")
    ap.add_argument("--visibility", action="store_true", help="Measure Browser eye hide/show instead of navigation")
    args = ap.parse_args()
    os.environ.pop("QT_QPA_PLATFORM", None)
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="energy-navigation-")
    from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QApplication, QDockWidget
    from core.archenergy import configure_profile
    from main import _configure_surface_format, _init_language
    from views.main_window import MainWindow
    from views.theme import apply_theme
    _configure_surface_format()
    app = QApplication([])
    configure_profile()
    _init_language()
    apply_theme(app)
    window = MainWindow(defer_extensions=True)
    window.setAttribute(Qt.WA_ShowWithoutActivating, True)
    window.move(-32000, -32000)
    window.resize(1500, 950)
    vp = window.viewport
    report = {"ok": False, "refreshes": []}
    phase = "open"
    before = hashlib.sha256(args.model.read_bytes()).hexdigest()

    def measure_refresh(panel, label):
        original = panel.refresh
        def refresh(*a):
            started = time.perf_counter()
            result = original(*a)
            report["refreshes"].append({"panel": label, "phase": phase,
                "seconds": time.perf_counter()-started})
            return result
        panel.refresh = refresh

    def finish(error=None):
        if error:
            report["error"] = str(error)
        report["source_unchanged"] = hashlib.sha256(args.model.read_bytes()).hexdigest() == before
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        window._saved_version = vp.scene.version
        window.close()
        app.exit(0 if report["ok"] else 1)

    def gesture():
        p = QPointF(vp.width()*.5, vp.height()*.5)
        started = time.perf_counter()
        vp.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, p,
            Qt.MiddleButton, Qt.MiddleButton, Qt.NoModifier))
        pressed = time.perf_counter()-started
        for i in range(1, 4):
            vp.mouseMoveEvent(QMouseEvent(QEvent.MouseMove, p+QPointF(12*i, 4*i),
                Qt.NoButton, Qt.MiddleButton, Qt.NoModifier))
            vp.repaint()
            app.processEvents()
        vp.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, p+QPointF(36,12),
            Qt.MiddleButton, Qt.NoButton, Qt.NoModifier))
        return {"press_seconds": pressed, "three_frames_seconds": time.perf_counter()-started}

    def measure():
        nonlocal phase
        try:
            report["gl_info"] = getattr(vp, "gl_info", {})
            if args.visibility:
                browser = window.project_browser.outliner
                browser.refresh()
                group = max((g for g in vp.scene.groups if vp.scene.entity_visible(g)),
                            key=lambda g: len(g.mesh.faces))
                report["component"] = group.name
                report["visibility"] = []
                for i in range(4):
                    phase = "hide" if not group.hidden else "show"
                    profile = cProfile.Profile()
                    started = time.perf_counter()
                    profile.enable()
                    browser.toggle_hidden([group])
                    clicked = time.perf_counter()-started
                    for _ in range(3):
                        vp.repaint()
                        app.processEvents()
                    elapsed = time.perf_counter()-started
                    profile.disable()
                    stream = io.StringIO()
                    pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(32)
                    args.report.with_name(args.report.stem+f"-{i}-{phase}.txt").write_text(
                        stream.getvalue().rstrip()+"\n", encoding="utf-8")
                    report["visibility"].append({"action": phase, "click_seconds": clicked,
                        "including_frames_seconds": elapsed, "hidden": group.hidden})
                report["ok"] = not group.hidden
                finish()
                return
            phase = "navigate"
            report["first_gesture"] = gesture()
            report["warm_gesture"] = gesture()
            if args.sample:
                from tools.base import ToolContext
                from tools.paint import clicked_back_side
                from core.group import effective_material
                from core.materials import effective_attrs
                sample = None
                for fx, fy in ((.5,.5), (.4,.5), (.6,.5), (.3,.6), (.7,.6), (.5,.7)):
                    x, y = vp.width()*fx, vp.height()*fy
                    face, group = vp.pick_face_any(x, y)
                    if face is None:
                        continue
                    attrs = effective_attrs(face.attrs, effective_material(group))
                    if clicked_back_side(vp, face, group, x, y):
                        back = face.attrs.get("back")
                        if isinstance(back, dict):
                            attrs = back
                        elif back is not True:
                            attrs = {}
                    if attrs.get("mat") in vp.scene.materials:
                        sample = (x, y, attrs["mat"])
                        break
                assert sample is not None, "No named material hit in viewport"
                x, y, name = sample
                version, depth = vp.scene.version, len(vp.history.undo_stack)
                window._act_eyedropper.trigger()
                vp.active_tool.on_click(ToolContext(viewport=vp, world=None,
                    screen=QPointF(x,y), modifiers=Qt.NoModifier, snap=None))
                app.processEvents()
                palette = window.findChild(QDockWidget, "extension_archcontrol_materials").widget()
                assert palette.selected_name() == name
                assert vp.scene.version == version and len(vp.history.undo_stack) == depth
                report["eyedropper"] = {"name": name, "selected": palette.selected_name(), "read_only": True}
                palette.table.grab().save(str(args.report.with_suffix(".png")))
            phase = "enter_edit"
            group = max(vp.scene.groups, key=lambda g: len(g.mesh.faces))
            started = time.perf_counter()
            vp.begin_group_edit(group)
            vp.scene.selection = {vp.scene.mesh.faces[0]}
            vp.notify_scene_changed()
            for _ in range(4):
                app.processEvents()
                vp.repaint()
            report["edit_entry_seconds"] = time.perf_counter()-started
            phase = "navigate_in_edit"
            profile = cProfile.Profile()
            report["edit_first_gesture"] = profile.runcall(gesture)
            stream = io.StringIO()
            pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(25)
            args.report.with_suffix(".txt").write_text(stream.getvalue(), encoding="utf-8")
            report["edit_warm_gesture"] = gesture()
            report["ok"] = True
        except Exception:
            import traceback
            report["traceback"] = traceback.format_exc()
            finish("Navigation audit failed")
            return
        finish()

    def load():
        try:
            window.load_extensions()
            for name in ("archcontrol", "archcontrol_materials", "archcontrol_zones"):
                panel = window.findChild(QDockWidget, "extension_"+name).widget()
                measure_refresh(panel, name)
            if args.materials:
                dock = window.findChild(QDockWidget, "extension_archcontrol_materials")
                window.set_tray_shown(dock, True)
            if args.visibility:
                dock = window.findChild(QDockWidget, "tray_project_browser")
                window.set_tray_shown(dock, True)
            assert window.open_path(args.model) is not False
            window._on_zoom_extents()
            QTimer.singleShot(1500, measure)
        except Exception as exc:
            finish(exc)

    window.show()
    QTimer.singleShot(100, load)
    QTimer.singleShot(60000, lambda: finish("Navigation timed out"))
    app.exec()
    print(json.dumps({k: v for k, v in report.items() if k != "refreshes"}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
