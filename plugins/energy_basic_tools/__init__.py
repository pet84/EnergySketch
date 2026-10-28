# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""User-selected native/Codex/Arrow icons and paired toolbars."""
from pathlib import Path
import json

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

ICON_FILES = {
    'line': 'line', 'freehand': 'freehand', 'rectangle': 'rectangle',
    'rotated_rect': 'rotated-rectangle', 'circle': 'circle', 'polygon': 'polygon',
    'center_arc': 'arc-center', 'arc': 'arc-2-point', 'arc3': 'arc-3-point',
    'pie': 'pie', 'tape': 'tape-measure', 'protractor': 'protractor',
}
_mapping = Path(__file__).parent / 'icons.json'
if _mapping.is_file():
    ICON_FILES = json.loads(_mapping.read_text(encoding='utf-8'))
DRAW_ROWS = (('line', 'freehand'), ('rectangle', 'rotated_rect'),
             ('circle', 'polygon'), ('center_arc', 'arc'), ('arc3', 'pie'))
MEASURE_ROWS = (('tape', 'dimension'), ('protractor', 'text'), ('geopath', 'text3d'))


def register_icons():
    """Use the host's palette/accent and refresh route, including mini cursors."""
    from views import icons
    # Keep native functions on the host module so repeated registration and
    # reimporting this plugin can always restore the original vector drawings.
    if not hasattr(icons, '_energy_builtin_draw'):
        icons._energy_builtin_draw = dict(icons._DRAW)
    baseline = icons._energy_builtin_draw
    selection_file = Path(__file__).parent / 'selection.json'
    if selection_file.is_file():
        selection = json.loads(selection_file.read_text(encoding='utf-8'))
        for item in selection['choices']:
            if item['variant'] == 'energysketch' and item['key'] in baseline:
                icons._DRAW[item['key']] = baseline[item['key']]
    directory = Path(__file__).parent / 'svg'
    for key, filename in ICON_FILES.items():
        source = (directory / f'{filename}.svg').read_text(encoding='utf-8')

        def draw(painter, ink, template=source):
            data = template.replace('#252B33', ink.name()).replace(
                '#3288DF', icons._accent().name())
            renderer = QSvgRenderer(QByteArray(data.encode('utf-8')))
            painter.save()
            renderer.render(painter, QRectF(0, 0, icons._PX, icons._PX))
            painter.restore()

        icons._DRAW[key] = draw
    icons.clear_cursor_cache()


def _pair_bar(window, toolbar, rows):
    if getattr(toolbar, '_energy_paired', False):
        return
    original = list(toolbar.actions())
    for action in original:
        # Removing an action from a toolbar must not remove its shortcut's
        # widget association. The SAME action remains in its menu and group.
        if action not in window.actions():
            window.addAction(action)
        toolbar.removeAction(action)
    by_key = dict(window._tool_actions)
    by_key['text3d'] = window._act_3dtext
    used = set()
    toolbar._energy_buttons = []
    for keys in rows:
        row = QWidget(toolbar)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for key in keys:
            action = by_key[key]
            used.add(action)
            button = QToolButton(row)
            button.setObjectName(f'energy_tool_{key}')
            button.setDefaultAction(action)
            button.setAutoRaise(True)
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setIconSize(toolbar.iconSize())
            toolbar.iconSizeChanged.connect(button.setIconSize)
            layout.addWidget(button)
            toolbar._energy_buttons.append(button)
        toolbar.addWidget(row)
    # Preserve any additional actions supplied by a newer host/plugin.
    for action in original:
        if action not in used:
            toolbar.addAction(action)
    toolbar._energy_paired = True
    toolbar._energy_original_actions = original
    if window.toolBarArea(toolbar) != Qt.LeftToolBarArea:
        window.addToolBar(Qt.LeftToolBarArea, toolbar)


def apply(window):
    """Safe to repeat for a live window; never touches document/history data."""
    register_icons()
    window._refresh_toolbar_icons()
    _pair_bar(window, window.toolbars['draw'], DRAW_ROWS)
    _pair_bar(window, window.toolbars['annotate'], MEASURE_ROWS)


def setup(app):
    apply(app.window)
    from PySide6.QtWidgets import QApplication
    if QApplication.instance().property('energysketch_profile'):
        from core.archenergy_layout import install
        install(app.window)
