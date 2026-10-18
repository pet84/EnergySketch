# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Read-only frozen-bundle audit; no network, model writes or authentication."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--archenergy-check", type=Path)
    mode.add_argument("--archenergy-render", type=Path)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--csv-references", type=Path)
    args = parser.parse_args()
    if args.archenergy_render:
        return render_check(args)
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    stream = io.StringIO()
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel
        from PySide6.QtGui import QIcon
        from core.archenergy import configure_profile, user_data_dir
        from core.paths import app_root
        app = QApplication.instance() or QApplication([])
        configure_profile()
        from main import _init_language, _self_check
        _init_language()
        from core.i18n import current_language, tr
        root = app_root()
        with contextlib.redirect_stdout(stream):
            report["upstream_check_exit"] = _self_check()
        report["upstream_check"] = stream.getvalue()
        report["language"] = current_language()
        report["user_data_dir"] = str(user_data_dir())
        assert tr("File") == "Soubor" or current_language() != "cs"
        for name in ("help.html", "recommended_colors.json", "NOTICE"):
            assert Path(__file__).with_name(name).is_file(), name
        icon = QIcon(str(root / "resources/icons/energysketch.ico"))
        assert not icon.isNull()
        if getattr(sys,"frozen",False):
            from plugins.ai_bridge import mcp_command
            mcp_path=Path(mcp_command()[0])
            assert mcp_path.is_file(),str(mcp_path)
            report["mcp_executable"]=mcp_path.name
        report["icon_sizes"] = [f"{s.width()}x{s.height()}" for s in icon.availableSizes()]
        from views.about_dialog import AboutDialog
        about = AboutDialog(None, "QA")
        wordmark = about.findChild(QLabel, "energysketch-brand-logo")
        assert wordmark is not None and not wordmark.pixmap().isNull()
        report["approved_brand_logo"] = True
        about.credits._timer.stop()
        about.close()
        if current_language() == "cs":
            buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
            assert buttons.button(QDialogButtonBox.Cancel).text() == "Zrušit"
        from .adapter import _reader_package, parse_skp, face_records
        _reader_package()  # verifies physical source and private imports
        from .windows_ui import WindowGridDialog
        from .help_ui import HelpDialog
        from .materials_ui import MaterialDialog
        from .zones_ui import ZonePalette
        if args.model:
            source_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
            scene = parse_skp(args.model)
            faces = list(face_records(scene))
            from .core import triangulated_area
            report["model"] = {"sha256": source_hash, "faces": len(faces),
                               "materials": sorted(scene.materials),
                               "area_m2": sum(triangulated_area(f.triangles) for f in faces),
                               "source_unchanged": hashlib.sha256(args.model.read_bytes()).hexdigest() == source_hash}
            if args.csv_references:
                report["csv_acceptance"] = csv_check(scene, args.csv_references,
                                                     args.archenergy_check.with_suffix(""))
            report["section_slice"] = slice_check(scene)
        report["ok"] = report["upstream_check_exit"] == 0
    except Exception as exc:
        import traceback
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()
        report["upstream_check"] = stream.getvalue()
    args.archenergy_check.parent.mkdir(parents=True, exist_ok=True)
    args.archenergy_check.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return 0 if report["ok"] else 1


def slice_check(scene):
    """Exercise the same section-plane menu/service/history on a private scene."""
    from types import SimpleNamespace
    from PySide6.QtGui import QVector3D
    from PySide6.QtWidgets import QMenu
    from core.history import History
    from core.section import SectionPlane
    from .adapter import PanelService, face_records, section_slice_context_menu
    low, high = scene.bounds()
    assert low is not None and high is not None
    cut = SectionPlane((low+high)*.5, QVector3D(0,0,1), symbol="QA")
    scene.section_planes.append(cut)
    previous_selection = set(scene.selection)
    scene.selection = {cut}
    original_faces = len(list(face_records(scene)))
    history = History(scene)
    viewport = SimpleNamespace(history=history, notify_scene_changed=lambda: None, update=lambda: None)
    service = PanelService(SimpleNamespace(scene=scene, window=None, viewport=viewport))
    try:
        menu = QMenu()
        section_slice_context_menu(service, menu, [cut])
        assert any(action.text() == "Vytvořit skupinu z průřezu" for action in menu.actions())
        group = service.create_section_slice(cut)
        report = {"ok": True, "edges": len(group.mesh.edges), "faces": len(group.mesh.faces),
                  "source_faces": original_faces, "name": group.name,
                  "max_distance_m": max(abs(cut.side(v.position)) for v in group.mesh.vertices)}
        assert report["edges"] > 0 and report["faces"] == 0
        assert report["max_distance_m"] < .0001
        assert len(list(face_records(scene))) == original_faces
        assert history.undo() and group not in scene.groups and scene.selection == {cut}
        assert history.redo() and group in scene.groups
        assert history.undo()
        return report
    finally:
        scene.section_planes.remove(cut)
        scene.selection = previous_selection


def csv_check(scene, references, output):
    """Exact CSV acceptance in the actual frozen binary, before/after IGZ."""
    from core.scene import Scene
    from formats.igz import load_into, save_scene
    from .adapter import face_records
    from .core import collect_rows
    from .exports import complex_csv, energy_csv, renovacni_pas_csv

    def exports(current):
        north = current.plugin_data["archcontrol"]["north_angle"]
        faces = list(face_records(current))
        rows = collect_rows(faces, north)["rows"]
        ds = current.plugin_data["archcontrol"].get("material_dictionaries", {})
        rp = {name: value.get("ArchControl_RP", {}) for name, value in ds.items()}
        return {"ArchControl_Export.csv": complex_csv(rows),
                "ArchControl_Energie_Zony_Export.csv": energy_csv(rows),
                "ArchControl_RenovacniPas.csv": renovacni_pas_csv(faces, north, rp)}

    output.mkdir(parents=True, exist_ok=True)
    path = output / "roundtrip.igz"
    save_scene(scene, path)
    restored = Scene()
    load_into(restored, path)
    report = {}
    for phase, current in (("imported", scene), ("reopened_igz", restored)):
        folder = output / phase
        folder.mkdir(exist_ok=True)
        report[phase] = {}
        for name, data in exports(current).items():
            (folder / name).write_bytes(data)
            reference = (references / name).read_bytes()
            report[phase][name] = {"byte_identical": data == reference,
                                  "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    assert all(result["byte_identical"] for phase in report.values() for result in phase.values()), report
    return report


def toolbar_theme_check(window, folder):
    """Verify live recolouring through the unmodified host theme API."""
    from PySide6.QtWidgets import QApplication
    from views import theme
    app = QApplication.instance()
    toolbar = window._archcontrol_toolbar
    mode, accent = theme.saved_theme(), theme.saved_accent()
    report = []
    try:
        for new_mode, new_accent in (("light", "blue"), ("dark", "blue"),
                                     ("light", "green"), ("dark", "purple")):
            theme.save_accent(new_accent)
            theme.apply_theme(app, new_mode)
            theme.apply_accent(app)
            QApplication.processEvents()
            ink = app.palette().windowText().color().rgba()
            highlight = theme.accent_color().rgba()
            for action in toolbar.actions():
                image = action.icon().pixmap(48, 48).toImage()
                colors = {image.pixelColor(x, y).rgba() for x in range(image.width())
                          for y in range(image.height())}
                assert ink in colors and highlight in colors, action.text()
            path = folder / f"archcontrol-toolbar-{new_mode}-{new_accent}.png"
            assert toolbar.grab().save(str(path))
            report.append({"theme": new_mode, "accent": new_accent,
                           "all_13_icons_recoloured": True, "image": str(path)})
    finally:
        theme.save_accent(accent)
        theme.apply_theme(app, mode)
        theme.apply_accent(app)
    return report


def render_check(args):
    """Real Windows OpenGL, own nonactivating window outside the visible desktop."""
    import tempfile
    os.environ.pop("QT_QPA_PLATFORM", None)
    os.environ["APPDATA"] = tempfile.mkdtemp(prefix="energysketch-render-")
    from PySide6.QtCore import QTimer, Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from core.archenergy import configure_profile
    from core.paths import app_root
    from main import _configure_surface_format, _init_language
    from views.theme import apply_theme
    from views.main_window import MainWindow
    _configure_surface_format()
    app = QApplication([])
    configure_profile()
    _init_language()
    apply_theme(app)
    app.setWindowIcon(QIcon(str(app_root() / "resources/icons/energysketch.ico")))
    window = MainWindow(defer_extensions=True)
    window.setAttribute(Qt.WA_ShowWithoutActivating, True)
    window.move(-32000, -32000)
    window.resize(1400, 950)
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)), "network_requested": False}
    from views.theme import saved_theme, saved_accent
    from views.icons import toolbar_icon_px
    report["appearance"] = {"theme": saved_theme(), "accent": saved_accent(), "toolbar_icon_px": toolbar_icon_px()}
    source_hash = hashlib.sha256(args.model.read_bytes()).hexdigest() if args.model else None
    completed = False

    def finish(error=None):
        nonlocal completed
        if completed:
            return
        completed = True
        if error:
            report["error"] = str(error)
        if args.model:
            report["source_unchanged"] = hashlib.sha256(args.model.read_bytes()).hexdigest() == source_hash
        args.archenergy_render.parent.mkdir(parents=True, exist_ok=True)
        args.archenergy_render.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        window._saved_version = window.viewport.scene.version
        window.close()
        app.exit(0 if report["ok"] else 1)

    def capture():
        try:
            vp = window.viewport
            context = vp.context()
            assert context is not None and context.isValid(), "OpenGL context is invalid"
            frame = vp.grabFramebuffer()
            assert not frame.isNull(), "Empty OpenGL framebuffer"
            image_path = args.archenergy_render.with_suffix(".png")
            assert frame.save(str(image_path))
            colors = {frame.pixel(x, y) for x in range(0,frame.width(),max(1,frame.width()//30))
                      for y in range(0,frame.height(),max(1,frame.height()//30))}
            assert len(colors) > 5, "Framebuffer contains no distinguishable model"
            from .adapter import face_records
            report.update(ok=True, title=window.windowTitle(),
                          gl_info=getattr(vp, "gl_info", {}),
                          framebuffer=[frame.width(),frame.height()], sampled_colors=len(colors),
                          faces=len(list(face_records(vp.scene))), materials=len(vp.scene.materials),
                          image=str(image_path))
            errors = window._extension_load_errors
            report["extension_load_errors"] = errors
            assert not errors, str(errors)
            from PySide6.QtWidgets import QDockWidget
            toolbar = window._archcontrol_toolbar
            assert toolbar.isVisibleTo(window), "ArchControl toolbar is hidden"
            assert len(toolbar.actions()) == 13
            assert all(not action.icon().isNull() for action in toolbar.actions())
            toolbar_image = args.archenergy_render.with_name("archcontrol-toolbar.png")
            assert toolbar.grab().save(str(toolbar_image))
            material_table = window.findChild(QDockWidget, "extension_archcontrol_materials").widget().table
            assert material_table.columnCount() == 9 and material_table.horizontalHeaderItem(8).text() == "Akce"
            # Extensions use private module namespaces; look up the stable
            # dock name rather than importing a second, different Python class.
            from PySide6.QtCore import QRect
            from PySide6.QtGui import QColor, QImage, QPainter
            from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
            surface_panel = window.findChild(QDockWidget, "extension_archcontrol").widget()
            surface_panel.refresh()
            if surface_panel.table.rowCount():
                cell = surface_panel.table.item(0, 13)
                assert cell.background().color() == QColor(cell.text())
                option = QStyleOptionViewItem()
                option.rect = QRect(0, 0, 160, 28)
                option.palette = app.palette()
                option.state = QStyle.State_Enabled | QStyle.State_Selected
                swatch = QImage(160, 28, QImage.Format_ARGB32)
                swatch.fill(QColor("magenta"))
                painter = QPainter(swatch)
                surface_panel.table.itemDelegateForColumn(13).paint(
                    painter, option, surface_panel.table.model().index(0, 13))
                painter.end()
                assert swatch.pixelColor(145, 14) == QColor(cell.text())
            report["surface_color_column"] = {"swatches": True, "selection_preserves_color": True}
            north_action = next(action for action in toolbar.actions() if action.objectName() == "archcontrol_north")
            north_action.trigger()
            assert vp.active_tool.name == "ArchControl — Sever dvěma body"
            vp.active_tool.on_cancel(vp)
            report["archcontrol_toolbar"] = {
                "visible": True, "icons": len(toolbar.actions()),
                "icon_size": toolbar.iconSize().width(), "north_tool_activated": True,
                "material_action_column": True, "image": str(toolbar_image),
            }
            report["toolbar_live_themes"] = toolbar_theme_check(window, args.archenergy_render.parent)
            if args.model:
                report["eyedropper"] = eyedropper_check(window)
        except Exception as exc:
            report["ok"] = False
            import traceback
            report["traceback"] = traceback.format_exc()
            finish(exc)
            return
        finish()

    def load():
        try:
            window.load_extensions()
            if args.model:
                assert window.open_path(args.model) is not False, "Standard model opening failed"
            window._on_zoom_extents()
            QTimer.singleShot(1800, capture)
        except Exception as exc:
            finish(exc)

    window.show()
    QTimer.singleShot(100, load)
    QTimer.singleShot(45000, lambda: finish("Rendering timed out"))
    app.exec()
    return 0 if report["ok"] else 1


def eyedropper_check(window):
    """Actual viewport pick → native tool → extension signal → palette row."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtWidgets import QApplication, QDockWidget
    from core.group import effective_material
    from core.materials import effective_attrs
    from tools.base import ToolContext
    from tools.paint import clicked_back_side
    vp = window.viewport
    for fx, fy in ((.5,.5), (.4,.5), (.6,.5), (.3,.6), (.7,.6), (.5,.7), (.5,.4)):
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
        name = attrs.get("mat")
        if name not in vp.scene.materials:
            continue
        version, undo = vp.scene.version, len(vp.history.undo_stack)
        window._act_eyedropper.trigger()
        vp.active_tool.on_click(ToolContext(viewport=vp, world=None,
            screen=QPointF(x,y), modifiers=Qt.NoModifier, snap=None))
        QApplication.processEvents()
        palette = window.findChild(QDockWidget, "extension_archcontrol_materials").widget()
        assert palette.selected_name() == name, "Eyedropper did not reveal the material"
        assert palette.table.selectedItems()
        assert vp.scene.version == version and len(vp.history.undo_stack) == undo
        return {"ok": True, "name": name, "read_only": True,
                "palette_rows": palette.table.rowCount()}
    raise AssertionError("No named material could be sampled from the viewport")
