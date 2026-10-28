# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""The approved workspace uses existing actions and preserves saved layouts."""
import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QDockWidget, QLabel, QMainWindow, QTabBar, QToolBar
from core import archenergy_layout as layout


@pytest.fixture
def workspace(tmp_path,monkeypatch):
    settings = QSettings(str(tmp_path/'layout.ini'),QSettings.IniFormat)
    monkeypatch.setattr(layout,'QSettings',lambda:settings)
    window = QMainWindow()
    window.resize(2256,1180)
    window.setCentralWidget(QLabel('Model stays here'))
    window._mark_trays_known = lambda store,names: store.setValue('ui/known_trays',names)
    for name in [n for row in layout.TOP_ROWS for n in row]+list(layout.LEFT_COLUMN):
        bar = QToolBar(name,window)
        bar.setObjectName(name)
        action = QAction(name,window)
        action.setShortcut('Ctrl+L' if name=='draw' else '')
        bar.addAction(action)
        window.addToolBar(Qt.BottomToolBarArea,bar)
    for name in layout.RIGHT_TABS+('extension_render_blender',):
        dock = QDockWidget(name,window)
        dock.setObjectName(name)
        dock.setWidget(QLabel(name))
        window.addDockWidget(Qt.LeftDockWidgetArea,dock)
    window.show()
    QApplication.processEvents()
    yield window,settings
    window.close()
    QApplication.processEvents()


def test_two_top_rows_and_left_column_preserve_action_identity(workspace):
    window,_ = workspace
    before = {bar.objectName():bar.actions()[0] for bar in window.findChildren(QToolBar)}
    layout.arrange_toolbars(window)
    QApplication.processEvents()
    bars = {bar.objectName():bar for bar in window.findChildren(QToolBar)}
    top = sorted((bar for bar in bars.values() if window.toolBarArea(bar)==Qt.TopToolBarArea),key=lambda b:(b.y(),b.x()))
    assert [bar.objectName() for bar in top] == ['main','modify','views','view','sections','panels_toolbar','solids','archcontrol_tools_toolbar','layers']
    assert len({bar.y() for bar in top}) == 2
    assert all(window.toolBarArea(bars[name])==Qt.LeftToolBarArea for name in ('draw','annotate','walkthrough'))
    assert all(bar.actions()[0] is before[name] for name,bar in bars.items())
    assert bars['draw'].actions()[0].shortcut().toString() == 'Ctrl+L'


def test_existing_saved_layout_is_not_replaced(workspace):
    window,settings = workspace
    initial = window.saveState()
    settings.setValue('ui/window_state',initial)
    layout.install(window)
    QApplication.processEvents()
    assert window.saveState() == initial
    assert settings.value('ui/window_state') == initial


def test_first_launch_waits_for_extensions_and_saves_the_new_default(workspace):
    window,settings = workspace
    settings.setValue('ui/energy_factory_pending',True)
    layout.install(window)
    for _ in range(5):
        QApplication.processEvents()
    assert not settings.contains('ui/energy_factory_pending')
    assert settings.value('ui/energy_factory_revision',type=int) == 1
    assert settings.value('ui/window_state') is not None
    dock = window.findChild(QDockWidget,'extension_archcontrol')
    assert window.dockWidgetArea(dock) == Qt.RightDockWidgetArea
    tabbar = next(bar for bar in window.findChildren(QTabBar) if bar.count()==11)
    assert tabbar.tabText(tabbar.currentIndex()) == 'extension_archcontrol'
    assert [tabbar.tabText(i) for i in range(tabbar.count())] == list(layout.RIGHT_TABS)
    assert window.findChild(QDockWidget,'extension_render_blender').isHidden()
