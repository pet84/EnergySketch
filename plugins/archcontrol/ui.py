# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Qt presentation only. All host/document calls pass through PanelService."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from .core import HEADERS, EXPORT_INDICES, aggregate_rows
from .materials_ui import MaterialColorDelegate
from .panel_refresh import DeferredReportPanel


class ArchControlPanel(DeferredReportPanel):
    def __init__(self, service):
        super().__init__()
        self.service = service
        self._data = None
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)
        tools = QHBoxLayout()
        self.refresh_button = QPushButton("Obnovit")
        self.refresh_button.clicked.connect(self.refresh)
        tools.addWidget(self.refresh_button)
        self.aggregate = QCheckBox("Sčítat stejné")
        self.aggregate.setChecked(True)
        self.aggregate.toggled.connect(self.fill_table)
        tools.addWidget(self.aggregate)
        self.show_rp = QCheckBox("RP")
        self.show_rp.toggled.connect(self.toggle_rp)
        tools.addWidget(self.show_rp)
        tools.addStretch()
        layout.addLayout(tools)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtr ploch…")
        self.filter.textChanged.connect(self.fill_table)
        layout.addWidget(self.filter)
        north = QHBoxLayout()
        north.addWidget(QLabel("Sever [° proti směru hodinových ručiček]:"))
        self.north_field = QLineEdit()
        self.north_field.setMaximumWidth(85)
        self.north_field.setPlaceholderText("neznámý")
        north.addWidget(self.north_field)
        confirm = QPushButton("Potvrdit")
        confirm.clicked.connect(self.confirm_north)
        north.addWidget(confirm)
        two_points = QPushButton("Dva body")
        two_points.clicked.connect(lambda: self.service.start_north_tool())
        north.addWidget(two_points)
        layout.addLayout(north)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        labels = HEADERS + ["RP kategorie", "RP typ", "RP etapa", "RP klient", "RP lze zateplit"]
        self.table = QTableWidget(0, len(labels))
        self.table.setHorizontalHeaderLabels(labels)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setItemDelegateForColumn(HEADERS.index("Barva"), MaterialColorDelegate(self.table))
        self.table.setColumnHidden(14, True)
        self.toggle_rp(False)
        layout.addWidget(self.table, 1)
        face_actions = QHBoxLayout()
        for label, callback in (("Vybrat plochy", self.select_rows), ("Skrýt", self.hide_rows),
                                ("Zobrazit vše", self.show_all), ("Upravit materiál", self.edit_material)):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, fn=callback: self.run_action(fn))
            face_actions.addWidget(button)
        layout.addLayout(face_actions)
        self.report = QLabel()
        self.report.setWordWrap(True)
        self.report.setTextInteractionFlags(Qt.TextSelectableByMouse)
        report_area = QScrollArea()
        report_area.setWidgetResizable(True)
        report_area.setMaximumHeight(160)
        report_area.setMinimumHeight(45)
        report_area.setWidget(self.report)
        layout.addWidget(report_area)
        copy_button = QPushButton("Kopírovat report EP / CV a zóny")
        copy_button.clicked.connect(lambda: QApplication.clipboard().setText(self.report.text()))
        layout.addWidget(copy_button)
        exports = QHBoxLayout()
        self.export_buttons = []
        for kind, label in (("complex", "Komplexní CSV"), ("energy", "Energie — zóny"), ("rp", "Renovační pas")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, key=kind: self.export_dialog(key))
            self.export_buttons.append(button)
            exports.addWidget(button)
        layout.addLayout(exports)

    def refresh(self):
        self._report_dirty = False
        north = self.service.north()
        self.north_field.setText("" if north is None else f"{north:g}")
        try:
            if north is None:
                raise ValueError("Pro výpočet orientace potvrďte sever modelu.")
            self._data = self.service.data()
            self.status.setText(f"Ploch v tabulce: {len(self._data['rows'])}; bez materiálu: {self._data['no_material_area']:.2f} m²")
            reports = self._data["reports"]
            lines = [f"EP: {sum(reports['ep'].values()):.2f} m²; CV: {sum(reports['cv'].values()):.2f} m²"]
            for zone in sorted(reports["envelope"].keys() | reports["ab"].keys() | reports["ep"].keys() | reports["cv"].keys()):
                lines.append(f"{zone}: obálka {reports['envelope'].get(zone, 0):.2f} m²; AB {reports['ab'].get(zone, 0):.2f} m²; EP {reports['ep'].get(zone, 0):.2f} m²; CV {reports['cv'].get(zone, 0):.2f} m²")
            if "zone_table" in self._data:
                from .zones import report_text
                lines.append(report_text(self._data["zone_table"]))
            self.report.setText("\n".join(lines))
        except (ValueError, KeyError) as exc:
            self._data = None
            self.status.setText(str(exc))
            self.report.clear()
        for button in self.export_buttons:
            button.setEnabled(self._data is not None)
        self.fill_table()

    def fill_table(self, *_args):
        self.table.setSortingEnabled(False)
        rows = self._data["rows"] if self._data else []
        if self.aggregate.isChecked():
            rows = aggregate_rows(rows)
        needle = self.filter.text().casefold()
        rows = [row for row in rows if needle in "\t".join(str(v) for v in row).casefold()]
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, index in enumerate(EXPORT_INDICES + [16, 17, 18, 19, 20, 21]):
                value = row[index]
                item = QTableWidgetItem()
                if j in (2, 4, 5, 7, 9, 11) and str(value):
                    try:
                        item.setData(Qt.DisplayRole, float(value))
                    except (ValueError, TypeError):
                        item.setText(str(value))
                else:
                    item.setText(str(value))
                if j == HEADERS.index("Barva"):
                    color = QColor(str(value))
                    if color.isValid():
                        item.setBackground(color)
                        item.setForeground(QColor("black" if color.lightness() > 128 else "white"))
                        item.setToolTip(f"Barva materiálu: {value}")
                if j == 0:
                    item.setData(Qt.UserRole, {"pids": str(row[16]), "material": str(row[13])})
                self.table.setItem(i, j, item)
        self.table.setSortingEnabled(True)

    def toggle_rp(self, show):
        for column in range(15, 20):
            self.table.setColumnHidden(column, not show)

    def selected_rows(self):
        rows = sorted({index.row() for index in self.table.selectedIndexes()})
        if not rows:
            raise ValueError("Vyberte řádek nebo více řádků tabulky.")
        return [self.table.item(row, 0).data(Qt.UserRole) for row in rows]

    def selected_pids(self):
        return "|".join(row["pids"] for row in self.selected_rows())

    def run_action(self, fn):
        try:
            fn()
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "ArchControl", str(exc))

    def select_rows(self):
        self.service.select_faces(self.selected_pids())

    def hide_rows(self):
        self.service.set_faces_hidden(self.selected_pids(), True)
        self.refresh()

    def show_all(self):
        self.service.show_all_faces()
        self.refresh()

    def edit_material(self):
        from .materials_ui import MaterialDialog
        rows = self.selected_rows()
        names = {row["material"] for row in rows}
        if len(names) != 1:
            raise ValueError("Pro úpravu vyberte plochy jednoho materiálu.")
        name = next(iter(names))
        material = next((m for m in self.service.materials() if m["name"] == name), None)
        if material is None:
            raise ValueError("Materiál už neexistuje. Obnovte tabulku.")
        MaterialDialog(self.service, material, "|".join(row["pids"] for row in rows), self).exec()
        self.refresh()

    def confirm_north(self):
        try:
            value = float(self.north_field.text().replace(",", "."))
            self.service.set_north(value)
            self.refresh()
        except ValueError as exc:
            QMessageBox.warning(self, "Sever modelu", str(exc))

    def export_dialog(self, kind):
        names = {"complex": "ArchControl_Export.csv", "energy": "ArchControl_Energie_Zony_Export.csv", "rp": "ArchControl_RenovacniPas.csv"}
        path, _ = QFileDialog.getSaveFileName(self, "Uložit export", names[kind], "CSV (*.csv)")
        if not path:
            return
        try:
            self.service.export(kind, path)
            self.status.setText(f"Export uložen: {path}")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Export CSV", str(exc))
