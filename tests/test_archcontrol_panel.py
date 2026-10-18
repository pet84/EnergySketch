# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
from dataclasses import replace
from types import SimpleNamespace
import pytest

from plugins.archcontrol.core import FaceRecord, collect_rows
from plugins.archcontrol.ui import ArchControlPanel


class Service:
    angle = 0

    def north(self):
        return self.angle

    def set_north(self, value):
        self.angle = value

    def data(self):
        face = FaceRecord("one", (((0, 0, 0), (2, 0, 0), (0, 1, 0)),),
                          (0, 1, 0), "SO-1-U0.3", parent_name="Zóna")
        return collect_rows([face, replace(face, pid="two")], self.angle)


def test_table_aggregation_filter_and_optional_rp_columns():
    panel = ArchControlPanel(Service())
    panel.refresh()
    assert panel.table.columnCount() == 20
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 9).data(0) == 2.0
    panel.aggregate.setChecked(False)
    assert panel.table.rowCount() == 2
    panel.filter.setText("Nenalezená konstrukce")
    assert panel.table.rowCount() == 0
    panel.filter.setText("SO-1")
    assert panel.table.rowCount() == 2
    assert panel.table.isColumnHidden(15)
    panel.show_rp.setChecked(True)
    assert not panel.table.isColumnHidden(15)


def test_unknown_north_does_not_export_assumed_or_stale_results():
    service = Service()
    panel = ArchControlPanel(service)
    panel.refresh()
    assert panel.table.rowCount() == 1
    service.angle = None
    panel.refresh()
    assert panel.table.rowCount() == 0
    assert all(not button.isEnabled() for button in panel.export_buttons)
    assert panel.north_field.text() == ""


def test_north_confirmation_updates_orientation():
    service = Service()
    panel = ArchControlPanel(service)
    panel.refresh()
    panel.north_field.setText("90,0")
    panel.confirm_north()
    assert service.angle == 90
    assert panel.table.item(0, 10).text() == "V"


def test_native_georef_clockwise_north_is_converted_to_ruby_convention():
    from plugins.archcontrol.adapter import PanelService
    app = SimpleNamespace(window=None, scene=SimpleNamespace(georef=SimpleNamespace(north=33.5)),
                          document_data=lambda **_: {})
    service = PanelService(app)
    assert service.north() == -33.5


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("selected", [False, True])
@pytest.mark.parametrize("color", ["#fdd835", "#5dcafd", "#1b1f23"])
def test_surface_table_renders_material_colors_even_when_selected(theme, selected, color):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtWidgets import QStyle, QStyleOptionViewItem
    from views.theme import apply_theme, saved_theme
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    previous = saved_theme()
    panel = None
    try:
        apply_theme(app, theme)
        service = Service()
        original = service.data
        def data():
            result = original()
            result["rows"][0][15] = color
            return result
        service.data = data
        panel = ArchControlPanel(service)
        panel.refresh()
        index = panel.table.model().index(0, 13)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 160, 28)
        option.palette = app.palette()
        option.state = QStyle.State_Enabled | (QStyle.State_Selected if selected else QStyle.State_None)
        image = QImage(160, 28, QImage.Format_ARGB32)
        image.fill(QColor("magenta"))
        painter = QPainter(image)
        panel.table.itemDelegateForColumn(13).paint(painter, option, index)
        painter.end()
        assert image.pixelColor(145, 14).name() == color
        assert panel.table.item(0, 13).text() == color
        ink = "black" if QColor(color).lightness() > 128 else "white"
        assert panel.table.item(0, 13).foreground().color() == QColor(ink)
    finally:
        if panel is not None:
            panel.close()
        apply_theme(app, previous)
