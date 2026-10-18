# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Native window-grid form; geometry and host operations live elsewhere."""
from PySide6.QtCore import QLocale
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)
from .windows import Grid, window_material


class Preview(QWidget):
    def __init__(self, dialog):
        super().__init__(dialog)
        self.dialog = dialog
        self.setMinimumHeight(180)

    def paintEvent(self, event):
        grid = self.dialog.parameters()
        rectangles = grid.rectangles((0., 0., 0.), (0., 0., 1.))
        pts = [p for rect in rectangles for p in rect]
        xmin, xmax = min(p[0] for p in pts), max(p[0] for p in pts)
        ymin, ymax = min(p[1] for p in pts), max(p[1] for p in pts)
        scale = min((self.width()-20)/max(xmax-xmin, 1e-9),
                    (self.height()-20)/max(ymax-ymin, 1e-9))
        color = self.dialog.material.currentData() or "#9e9e9e"
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#f1f3f4"))
        painter.setBrush(QColor(color))
        painter.setPen(QColor("#444444"))
        from PySide6.QtCore import QRectF
        for rect in rectangles:
            x, y, _ = rect[0]
            painter.drawRect(QRectF(10+(x-xmin)*scale, 10+(y-ymin)*scale,
                                    grid.width*scale, grid.height*scale))
        painter.end()


class WindowGridDialog(QDialog):
    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("ArchControl — Vložit mřížku oken na fasádu")
        self.resize(560, 550)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        previous = getattr(service, "window_grid_parameters", Grid())
        self.fields = {}
        for key, label in (("cols", "Počet sloupců"), ("rows", "Počet řad"),
                           ("width", "Šířka okna [m]"), ("height", "Výška okna [m]"),
                           ("gap_h", "Vodorovná mezera [m]"), ("gap_v", "Svislá mezera [m]")):
            if key in ("cols", "rows"):
                field = QSpinBox()
                field.setRange(1, 50)
            else:
                field = QDoubleSpinBox()
                field.setDecimals(4)
                field.setLocale(QLocale("cs_CZ"))
                field.setRange(-10000 if key.startswith("gap") else .0001, 10000)
                field.setSingleStep(.1)
            field.setValue(getattr(previous, key))
            self.fields[key] = field
            form.addRow(label, field)
        self.material = QComboBox()
        form.addRow("Materiál okna", self.material)
        row = QHBoxLayout()
        for label, callback in (("Nový materiál…", self.new_material), ("Obnovit seznam", self.refresh_materials)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        self.refresh_materials()
        if previous.material:
            self.material.setCurrentIndex(max(0, self.material.findText(previous.material)))
        elif self.material.count() > 1:
            self.material.setCurrentIndex(1)
        self.preview = Preview(self)
        layout.addWidget(self.preview)
        self.info = QLabel()
        layout.addWidget(self.info)
        note = QLabel("Klikněte do středu mřížky na fasádě. Vzniknou plochy s materiálem "
                      "na obou stranách; tloušťka stěny se neprořezává. Rozměry se řídí "
                      "místními osami komponenty stejně jako v původním pluginu.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        insert = buttons.addButton("Vložit — kliknout na fasádu", QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for field in self.fields.values():
            field.valueChanged.connect(self.refresh_preview)
        self.material.currentIndexChanged.connect(self.refresh_preview)
        self.refresh_preview()

    def parameters(self):
        return Grid(**{key: field.value() for key, field in self.fields.items()},
                    material=self.material.currentText() if self.material.currentIndex() > 0 else "")

    def refresh_preview(self, *_):
        if not hasattr(self, "preview"):
            return
        grid = self.parameters()
        w, h = grid.size
        self.info.setText(f"{grid.cols} × {grid.rows} = {grid.cols*grid.rows} oken; "
                          f"celkem {w:.2f} × {h:.2f} m; plocha oken "
                          f"{grid.cols*grid.rows*grid.width*grid.height:.2f} m²")
        self.preview.update()

    def refresh_materials(self):
        previous = self.material.currentText()
        self.material.clear()
        self.material.addItem("— bez materiálu —", "#9e9e9e")
        for row in sorted(self.service.materials(), key=lambda m: m["name"].lower()):
            if window_material(row["name"]):
                self.material.addItem(row["name"], row["color"])
        self.material.setCurrentIndex(max(0, self.material.findText(previous)))

    def new_material(self):
        from .materials_ui import MaterialDialog
        dialog = MaterialDialog(self.service, parent=self)
        dialog.typ.setCurrentIndex(dialog.typ.findData("OD"))
        dialog.exec()
        self.refresh_materials()

    def accept(self):
        grid = self.parameters()
        if not grid.material and QMessageBox.question(
                self, "Materiál okna", "Vložit okna bez energetického materiálu?") != QMessageBox.Yes:
            return
        self.service.window_grid_parameters = grid
        self.service.start_window_tool(grid)
        super().accept()
