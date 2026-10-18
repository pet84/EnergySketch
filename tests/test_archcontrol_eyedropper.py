# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
import copy
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QVector3D
from PySide6.QtWidgets import QApplication, QDockWidget
from tools.base import ToolContext
from tools.paint import PaintTool
from tests.test_archcontrol_materials import setup_scene, OLD, BACK


@pytest.mark.parametrize("side", ["front", "back", "inherited", "default"])
def test_native_eyedropper_reveals_exact_archcontrol_material_without_edit(side):
    from views.main_window import MainWindow
    window = MainWindow(defer_extensions=True)
    previous = (PaintTool.current_material, PaintTool.sample_armed,
                PaintTool.current_is_default, PaintTool.current_color)
    try:
        window.load_extensions()
        vp = window.viewport
        scene, history, _service, face = setup_scene()
        vp.scene, vp.history = scene, history
        group = scene.groups[0]
        expected = BACK if side == "back" else OLD
        if side in ("inherited", "default"):
            face.attrs.clear()
        if side == "inherited":
            group.material = scene.materials[OLD].face_attrs()
        if side == "default":
            expected = None
        dock = window.findChild(QDockWidget, "extension_archcontrol_materials")
        palette = dock.widget()
        palette.refresh()
        palette.table.sortItems(0, Qt.DescendingOrder)
        palette.filter.setText("does-not-match-anything")
        palette.only_used.setChecked(True)
        snapshot = copy.deepcopy(face.attrs)
        version, depth = scene.version, len(history.undo_stack)
        vp.pick_face_any = lambda *_: (face, group)
        vp._pixel_to_ray = lambda *_: (QVector3D(0, 0, 2),
                                      QVector3D(0, 0, 1 if side == "back" else -1))
        PaintTool.sample_armed = True
        PaintTool().on_click(ToolContext(viewport=vp, world=QVector3D(),
            screen=QPointF(12, 12), modifiers=Qt.NoModifier, snap=None))
        assert palette.selected_name(required=False) == expected
        if expected:
            assert palette.table.selectedItems()
            assert expected in palette.status.text()
            assert palette.filter.text() == ""
            assert not palette.only_used.isChecked()
        else:
            assert not palette.table.selectedItems()
            assert "nemá pojmenovaný" in palette.status.text()
        assert not dock.isHidden()
        assert face.attrs == snapshot
        assert scene.version == version and len(history.undo_stack) == depth
    finally:
        (PaintTool.current_material, PaintTool.sample_armed,
         PaintTool.current_is_default, PaintTool.current_color) = previous
        window._saved_version = window.viewport.scene.version
        window.close()


def test_hidden_reports_wait_for_show_and_camera_drag_to_finish():
    from PySide6.QtTest import QTest
    from plugins.archcontrol.panel_refresh import DeferredReportPanel
    class Panel(DeferredReportPanel):
        def __init__(self):
            super().__init__()
            self.calls = 0
            self.viewport = SimpleNamespace(_last_pos=None)
            self.service = SimpleNamespace(app=SimpleNamespace(viewport=self.viewport))
        def refresh(self):
            self.calls += 1
    panel = Panel()
    try:
        for _ in range(3):
            panel.schedule_refresh()
        QApplication.processEvents()
        assert panel.calls == 0
        panel.show()
        QApplication.processEvents()
        assert panel.calls == 1
        panel.viewport._last_pos = object()
        panel.schedule_refresh()
        QApplication.processEvents()
        assert panel.calls == 1
        panel.viewport._last_pos = None
        QTest.qWait(120)
        assert panel.calls == 2
    finally:
        panel.close()


def test_palette_refresh_preserves_existing_action_widgets_and_selection():
    from plugins.archcontrol.materials_ui import MaterialPalette
    _scene, _history, service, _face = setup_scene()
    palette = MaterialPalette(service)
    try:
        assert palette.select_sampled_material(OLD)
        row = palette.table.currentRow()
        actions = palette.table.cellWidget(row, 8)
        palette.refresh()
        assert palette.table.cellWidget(row, 8) is actions
        assert palette.selected_name() == OLD
    finally:
        palette.close()


def test_inactive_tabified_dock_updates_only_when_raised():
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMainWindow, QWidget
    from plugins.archcontrol.panel_refresh import DeferredReportPanel
    class Panel(DeferredReportPanel):
        def __init__(self):
            super().__init__()
            self.calls = 0
            self.service = SimpleNamespace()
        def refresh(self):
            self.calls += 1
    window = QMainWindow()
    panel = Panel()
    dock = QDockWidget("Report", window)
    dock.setWidget(panel)
    other = QDockWidget("Other", window)
    other.setWidget(QWidget())
    window.addDockWidget(Qt.RightDockWidgetArea, dock)
    window.addDockWidget(Qt.RightDockWidgetArea, other)
    window.tabifyDockWidget(dock, other)
    panel.bind_dock(dock)
    try:
        window.show()
        other.raise_()
        QTest.qWait(40)
        assert panel.isVisible() and panel.visibleRegion().isEmpty()
        panel.schedule_refresh()
        QApplication.processEvents()
        assert panel.calls == 0
        dock.raise_()
        QTest.qWait(40)
        assert panel.calls == 1
    finally:
        window.close()
