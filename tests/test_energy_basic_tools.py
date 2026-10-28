# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Paired bars keep the real actions, shortcuts, tool state and icon sizing."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMainWindow, QToolBar

from plugins.energy_basic_tools import DRAW_ROWS, MEASURE_ROWS, apply


@pytest.fixture
def window():
    app = QApplication.instance() or QApplication([])
    from plugins.archcontrol.icons import register_icons
    register_icons()
    win = QMainWindow()
    win._tool_actions = {}
    win.toolbars = {}
    group = QActionGroup(win)
    group.setExclusive(True)
    for bar_name, rows in [('draw', DRAW_ROWS), ('annotate', MEASURE_ROWS)]:
        bar = QToolBar(bar_name, win)
        bar.setIconSize(QSize(24,24))
        win.addToolBar(Qt.LeftToolBarArea, bar)
        win.toolbars[bar_name] = bar
        for row in rows:
            for key in row:
                action = QAction(key, win)
                action.setCheckable(True)
                group.addAction(action)
                bar.addAction(action)
                if key == 'text3d':
                    win._act_3dtext = action
                else:
                    win._tool_actions[key] = action
    win._tool_actions['line'].setShortcut('L')
    win._refresh_toolbar_icons = lambda: None
    yield win
    win.close()
    app.processEvents()


def test_pairing_keeps_actions_shortcuts_and_selection(window):
    line = window._tool_actions['line']
    apply(window)
    buttons = window.toolbars['draw']._energy_buttons
    assert [b.defaultAction().text() for b in buttons] == [k for row in DRAW_ROWS for k in row]
    assert buttons[0].defaultAction() is line
    assert line in window.actions()
    assert line.shortcut().toString() == 'L'
    buttons[0].click()
    assert line.isChecked()
    buttons[1].click()
    assert window._tool_actions['freehand'].isChecked()
    assert not line.isChecked()
    assert [b.defaultAction().text() for b in window.toolbars['annotate']._energy_buttons] == [k for row in MEASURE_ROWS for k in row]


def test_pairing_is_repeatable_and_tracks_icon_size(window):
    apply(window)
    buttons = window.toolbars['draw']._energy_buttons[:]
    apply(window)
    assert window.toolbars['draw']._energy_buttons == buttons
    assert len(window.toolbars['draw'].actions()) == 5
    window.toolbars['draw'].setIconSize(QSize(40,40))
    assert all(b.iconSize() == QSize(40,40) for b in buttons)


def test_svg_icons_render_for_all_twelve_tools(window):
    from views.icons import tool_icon
    from plugins.energy_basic_tools import ICON_FILES
    apply(window)
    for key in ICON_FILES:
        pixmap = tool_icon(key).pixmap(32,32)
        assert not pixmap.isNull(), key
        img = pixmap.toImage()
        assert any(img.pixelColor(x,y).alpha() for x in range(32) for y in range(32)), key


def test_approved_mix_restores_native_icons_and_renders_all_choices(window):
    import json
    from pathlib import Path
    from collections import Counter
    from views import icons
    from plugins import energy_basic_tools as plugin
    selection = json.loads((Path(plugin.__file__).parent / 'selection.json').read_text(encoding='utf-8'))
    choices = selection['choices']
    assert len({item['key'] for item in choices}) == 114
    assert Counter(item['variant'] for item in choices) == {'energysketch':44, 'codex':64, 'arrow':6}
    apply(window)
    for item in choices:
        key = item['key']
        if item['variant'] == 'energysketch':
            native = icons._energy_builtin_draw[key]
            assert icons._DRAW[key] is native, key
            # A previous live SVG registration must not stick after switching.
            icons._DRAW[key] = icons._DRAW['line']
            plugin.register_icons()
            assert icons._DRAW[key] is native, key
        else:
            assert key in plugin.ICON_FILES
        for size in (24, 40):
            image = icons.tool_icon(key).pixmap(size, size).toImage()
            assert not image.isNull(), key
            assert any(image.pixelColor(x,y).alpha() for x in range(size) for y in range(size)), (key,size)
