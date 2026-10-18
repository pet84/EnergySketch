# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Real plugin actions, late startup and user toolbar layout recovery."""
import hashlib

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QMenu, QToolBar

from plugins.archcontrol.toolbar import OBJECT_NAME, TITLE


@pytest.fixture
def windows():
    from views.main_window import MainWindow
    settings = QSettings()
    saved = {key: settings.value(key) for key in settings.allKeys()}
    settings.remove("ui/window_state")
    settings.remove("ui/window_geometry")
    owned = []

    def build():
        window = MainWindow(defer_extensions=True)
        owned.append(window)
        window.load_extensions()
        assert not window._extension_load_errors
        return window

    yield build
    for window in owned:
        window._saved_version = window.viewport.scene.version
        window.close()
    settings.clear()
    for key, value in saved.items():
        settings.setValue(key, value)


def actions(window):
    toolbar = window.findChild(QToolBar, OBJECT_NAME)
    window.show()
    QApplication.processEvents()
    return {action.objectName().removeprefix("archcontrol_"): action for action in toolbar.actions()}


def test_toolbar_is_visible_named_and_listed_separately_from_the_panel(windows):
    window = windows()
    toolbar = window.findChild(QToolBar, OBJECT_NAME)
    assert toolbar.windowTitle() == TITLE
    assert toolbar.isVisibleTo(window) and toolbar.isMovable() and toolbar.isFloatable()
    assert window.toolBarArea(toolbar) == Qt.TopToolBarArea
    assert len(actions(window)) == 13
    assert all(not action.icon().isNull() and "\n" in action.toolTip()
               for action in toolbar.actions())
    popup = window.createPopupMenu()
    assert toolbar.toggleViewAction() in popup.actions()
    toolbar.toggleViewAction().trigger()
    assert toolbar.isHidden()
    recovery = next(action for menu in window.findChildren(QMenu)
                    for action in menu.actions() if action.text() == "Vrátit lištu ArchControl nad model")
    recovery.trigger()
    assert not toolbar.isHidden() and window.toolBarArea(toolbar) == Qt.TopToolBarArea
    window.set_toolbar_icon_size(24)
    assert toolbar.iconSize().width() == 24


def test_icons_open_the_right_panels_and_north_tool_without_editing_model(windows):
    window = windows()
    version = window.viewport.scene.version
    for key, name in (("materials", "extension_archcontrol_materials"),
                      ("zones", "extension_archcontrol_zones"),
                      ("live", "extension_archcontrol_astra-live")):
        dock = window.findChild(QDockWidget, name)
        actions(window)[key].trigger()
        assert dock.isVisibleTo(window)
    actions(window)["north"].trigger()
    tool = window.viewport.active_tool
    assert tool.name == "ArchControl — Sever dvěma body"
    tool.on_cancel(window.viewport)
    assert window.viewport.scene.version == version
    assert window.viewport.active_tool.name == "Select"
    materials = window.findChild(QDockWidget, "extension_archcontrol_materials").widget()
    assert materials.table.columnCount() == 9
    assert materials.table.horizontalHeaderItem(8).text() == "Akce"


def test_menu_and_toolbar_share_the_same_actions_and_export_callbacks(windows, monkeypatch):
    # Discovery imports under a private name, so patch the actual widgets
    # loaded into this window rather than another import of the package.
    window = windows()
    panel = window.findChild(QDockWidget, "extension_archcontrol").widget()
    palette = window.findChild(QDockWidget, "extension_archcontrol_materials").widget()
    calls = []
    monkeypatch.setattr(panel, "export_dialog", lambda kind: calls.append(kind))
    monkeypatch.setattr(palette, "import_library", lambda: calls.append("library_import"))
    monkeypatch.setattr(palette, "export_library", lambda: calls.append("library_export"))
    for key in ("csv_complex", "csv_energy", "csv_rp", "library_import", "library_export"):
        action = actions(window)[key]
        assert any(action in menu.actions() for menu in action.associatedObjects()
                   if hasattr(menu, "actions") and menu is not window._archcontrol_toolbar)
        action.trigger()
    assert calls == ["complex", "energy", "rp", "library_import", "library_export"]


@pytest.mark.parametrize("hidden", [False, True])
def test_toolbar_position_and_visibility_survive_deferred_restart(windows, hidden):
    first = windows()
    toolbar = first._archcontrol_toolbar
    first.removeToolBar(toolbar)
    first.addToolBar(Qt.LeftToolBarArea, toolbar)
    toolbar.setVisible(not hidden)
    first._saved_version = first.viewport.scene.version
    first.close()  # saves actual QMainWindow state, as on a normal exit
    second = windows()
    assert second.toolBarArea(second._archcontrol_toolbar) == Qt.LeftToolBarArea
    assert second._archcontrol_toolbar.isHidden() is hidden
    second.load_extensions()
    assert len(second.findChildren(QToolBar, OBJECT_NAME)) == 1


@pytest.fixture
def appearance():
    from views import theme
    app = QApplication.instance()
    palette = app.palette()
    accent, mode = theme.saved_accent(), theme.saved_theme()
    yield theme
    theme.save_accent(accent)
    theme.save_theme(mode)
    theme.apply_theme(app, mode)
    app.setPalette(palette)


def pixels(icon, size=48):
    image = icon.pixmap(size, size).toImage()
    return {image.pixelColor(x, y).rgba() for x in range(image.width())
            for y in range(image.height()) if image.pixelColor(x, y).alpha() == 255}


@pytest.mark.parametrize("mode", ["light", "dark"])
@pytest.mark.parametrize("accent", ["orange", "blue", "green", "red", "purple", "yellow", "system"])
def test_every_custom_drawing_is_distinct_and_uses_the_host_ink_and_accent(appearance, mode, accent):
    from plugins.archcontrol.icons import DRAWINGS, register_icons
    from views.icons import tool_icon
    app = QApplication.instance()
    appearance.save_accent(accent)
    appearance.apply_theme(app, mode)
    register_icons()
    digests = set()
    for key in DRAWINGS:
        icon = tool_icon(f"archcontrol_{key}")
        colors = pixels(icon)
        assert app.palette().windowText().color().rgba() in colors, key
        assert appearance.accent_color().rgba() in colors, key
        image = icon.pixmap(48, 48).toImage()
        assert image.pixelColor(0, 0).alpha() == 0
        digests.add(hashlib.sha256(bytes(image.constBits())).hexdigest())
    assert len(digests) == 13


def test_open_toolbar_and_menu_icons_change_live_with_theme_and_accent(windows, appearance):
    window = windows()
    app = QApplication.instance()
    toolbar = window._archcontrol_toolbar
    initial_keys = [action.icon().cacheKey() for action in toolbar.actions()]
    for mode, accent in (("light", "green"), ("dark", "purple"), ("light", "blue")):
        appearance.save_accent(accent)
        appearance.apply_theme(app, mode)
        appearance.apply_accent(app)
        QApplication.processEvents()
        current_keys = [action.icon().cacheKey() for action in toolbar.actions()]
        assert all(before != after for before, after in zip(initial_keys, current_keys))
        initial_keys = current_keys
        for action in toolbar.actions():
            colors = pixels(action.icon())
            assert appearance.accent_color().rgba() in colors, action.text()
            assert app.palette().windowText().color().rgba() in colors, action.text()
            assert any(action in menu.actions() for menu in window.findChildren(QMenu))


def test_closed_floating_toolbar_can_be_recovered_over_the_model(windows):
    from tests.test_toolbar_float_close import _float
    window = windows()
    window.show()
    QApplication.processEvents()
    toolbar = window._archcontrol_toolbar
    _float(window, toolbar)
    toolbar.hide()
    recovery = next(action for menu in window.findChildren(QMenu)
                    for action in menu.actions() if action.text() == "Vrátit lištu ArchControl nad model")
    recovery.trigger()
    QApplication.processEvents()
    assert not toolbar.isFloating() and not toolbar.isHidden()
    assert window.toolBarArea(toolbar) == Qt.TopToolBarArea
