# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Component/zone palette with document-change refresh."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from .panel_refresh import DeferredReportPanel


class ZonePalette(DeferredReportPanel):
    def __init__(self, service):
        super().__init__()
        self.service = service
        layout = QVBoxLayout(self)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Název komponenty nebo zóny…")
        self.filter.textChanged.connect(self.refresh)
        layout.addWidget(self.filter)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Komponenta", "Číslo zóny", "Zóna", "Objem [m³]",
                                             "Obálka [m²]", "AB [m²]", "Po odpočtu AB [m²]", "Uzavřená", "Skrytá"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, action in (("Obnovit", self.refresh), ("Vybrat", self.select),
                              ("Skrýt / zobrazit", self.toggle_hidden), ("Kopírovat", self.copy)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=action: self.run(fn))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.status = QLabel("Objem je doložený pouze u uzavřeného tělesa. U otevřené komponenty je 0 jako v Ruby reportu.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh()

    def refresh(self, *_args):
        self._report_dirty = False
        old = self.selected_uid(required=False)
        needle = self.filter.text().casefold()
        rows = [row for row in self.service.zones() if needle in (row["name"] + " " + row["zone"]).casefold()]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = [row["name"], int(row["zoneNum"]), row["zone"], row["volume"],
                      row["m2"], row["m2ab"], row["m2net"], "Ano" if row["solid"] else "Ne",
                      "Ano" if row["hidden"] else "Ne"]
            for j, value in enumerate(values):
                item = QTableWidgetItem()
                item.setData(Qt.DisplayRole, value)
                if j == 0:
                    item.setData(Qt.UserRole, row["eid"])
                    item.setToolTip(row["defName"])
                self.table.setItem(i, j, item)
            if row["eid"] == old:
                self.table.selectRow(i)
        self.table.setSortingEnabled(True)

    def selected_uid(self, required=True):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            if required:
                raise ValueError("Vyberte komponentu v paletě.")
            return None
        return item.data(Qt.UserRole)

    def run(self, fn):
        try:
            fn()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "ArchControl — zóny", str(exc))

    def select(self):
        self.service.select_component(self.selected_uid())

    def toggle_hidden(self):
        self.service.toggle_component_hidden(self.selected_uid())
        self.refresh()

    def copy(self):
        lines = ["\t".join(self.table.horizontalHeaderItem(j).text() for j in range(self.table.columnCount()))]
        for i in range(self.table.rowCount()):
            lines.append("\t".join(self.table.item(i, j).text() for j in range(self.table.columnCount())))
        QApplication.clipboard().setText("\n".join(lines))
