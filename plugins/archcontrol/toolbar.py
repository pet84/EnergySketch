# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Movable ArchControl tools with original theme-aware flat drawings."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar


OBJECT_NAME = "archcontrol_tools_toolbar"
TITLE = "ArchControl — nástroje"


def create_toolbar(window, menu, commands):
    """Share actions with the menu; Qt saves placement/visibility by name.

    Commands are (stable key, label, description,
    callback). No copied document logic or extra side-panel buttons.
    """
    from views.icons import style_overflow_button, toolbar_icon_px, tool_icon
    from .icons import register_icons
    register_icons()

    toolbar = QToolBar(TITLE, window)
    toolbar.setObjectName(OBJECT_NAME)
    toolbar.setMovable(True)
    toolbar.setFloatable(True)
    toolbar.setAllowedAreas(Qt.AllToolBarAreas)
    px = toolbar_icon_px()
    toolbar.setIconSize(QSize(px, px))
    toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
    for key, label, description, callback in commands:
        icon_key = f"archcontrol_{key}"
        icon = tool_icon(icon_key)
        if icon.isNull():
            raise ValueError(f"Chybí kresba ikony ArchControl: {key}")
        action = QAction(icon, label, toolbar)
        action.setObjectName(f"archcontrol_{key}")
        action.setProperty("icon_key", icon_key)
        # The host redraws these on direct palette changes as well as on
        # Preferences -> Accent colour. Menus share these exact actions.
        window._icon_actions.append((action, icon_key))
        action.setStatusTip(description)
        action.setToolTip(f"{label}\n{description}")
        action.triggered.connect(lambda _checked=False, fn=callback: fn())
        toolbar.addAction(action)
        menu.addAction(action)

    # A separate row makes a newly installed bar visible even on a profile
    # that already fills the first row. A later restoreState honours the
    # user's own docked/floating location and hidden state instead.
    window.addToolBarBreak(Qt.TopToolBarArea)
    window.addToolBar(Qt.TopToolBarArea, toolbar)
    style_overflow_button(toolbar)
    menu.addSeparator()
    menu.addAction(toolbar.toggleViewAction())
    restore = menu.addAction("Vrátit lištu ArchControl nad model")
    restore.setStatusTip("Zobrazí ikony ArchControl nad modelem, i když se plovoucí lišta ztratila mimo obrazovku.")

    def bring_back():
        window.removeToolBar(toolbar)
        window.addToolBarBreak(Qt.TopToolBarArea)
        window.addToolBar(Qt.TopToolBarArea, toolbar)
        toolbar.show()

    restore.triggered.connect(bring_back)
    return toolbar
