# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""EnergySketch's default workspace, approved from Petr's reference image."""
from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtWidgets import QDockWidget, QToolBar

TOP_ROWS = (
    ('main', 'modify', 'views', 'view', 'sections', 'panels_toolbar', 'solids'),
    ('archcontrol_tools_toolbar', 'layers'),
)
LEFT_COLUMN = ('draw', 'annotate', 'walkthrough')
RIGHT_TABS = (
    'tray_properties', 'tray_bim', 'tray_georef', 'tray_project_browser',
    'extension_ai', 'extension_archcontrol', 'extension_archcontrol_materials',
    'extension_archcontrol_zones', 'extension_archcontrol_astra-live',
    'extension_solid_inspector', 'tray_layers',
)


def arrange_toolbars(window):
    """Reorder existing bars/actions, preserving all side panels and the model."""
    bars = {bar.objectName():bar for bar in window.findChildren(QToolBar)
            if bar.parent() is window}
    names = [name for row in TOP_ROWS for name in row] + list(LEFT_COLUMN)
    for name in names:
        if name in bars:
            window.removeToolBarBreak(bars[name])
            window.removeToolBar(bars[name])
    for index, row in enumerate(TOP_ROWS):
        if index:
            window.addToolBarBreak(Qt.TopToolBarArea)
        for name in row:
            if name in bars:
                window.addToolBar(Qt.TopToolBarArea,bars[name])
                bars[name].show()
    for name in LEFT_COLUMN:
        if name in bars:
            window.addToolBar(Qt.LeftToolBarArea,bars[name])
            bars[name].show()
    window.layout().activate()


def arrange_panels(window):
    """Seat the standard panels in the approved tab order; focus ArchControl."""
    docks = {dock.objectName():dock for dock in window.findChildren(QDockWidget)}
    ordered = [docks[name] for name in RIGHT_TABS if name in docks]
    if not ordered:
        return
    for dock in ordered:
        window.removeDockWidget(dock)
    for index,dock in enumerate(ordered):
        window.addDockWidget(Qt.RightDockWidgetArea,dock)
        if index:
            window.tabifyDockWidget(ordered[0],dock)
        dock.show()
    render = docks.get('extension_render_blender')
    if render is not None:
        render.hide()
    active = docks.get('extension_archcontrol',ordered[0])
    active.raise_()
    width = max(370,round((window.width()-88)*.44))
    window.resizeDocks([active],[width],Qt.Horizontal)
    settings = QSettings()
    settings.setValue('ui/hidden_trays',['extension_render_blender'])
    window._mark_trays_known(settings,list(docks))


def install(window):
    """First launch gets the factory layout; later user arrangements survive."""
    window._energy_default_toolbars = lambda: arrange_toolbars(window)
    window._energy_default_panels = lambda: arrange_panels(window)
    settings = QSettings()
    if not settings.value('ui/energy_factory_pending',False,type=bool):
        return

    def apply():
        arrange_toolbars(window)
        arrange_panels(window)

        def save():
            window.layout().activate()
            settings.setValue('ui/window_state',window.saveState())
            settings.remove('ui/energy_factory_pending')
            settings.setValue('ui/energy_factory_revision',1)
            settings.sync()
        QTimer.singleShot(0,window,save)
    # All extension bars and panels must exist before arranging them.
    QTimer.singleShot(0,window,apply)
