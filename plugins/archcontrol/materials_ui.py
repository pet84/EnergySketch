# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Native material form and palette; host calls only through the service."""
from PySide6.QtCore import Qt, QSize, QSignalBlocker
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QSlider, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QStyledItemDelegate,
    QStyle, QStyleOptionViewItem,
    QToolButton, QHeaderView,
    QAbstractItemView,
)
from .core import UN_VALUES
from .exports import RP_CATALOG, RP_FIELDS, read_rp
from .materials import TYPES, WINDOW_TYPES, RP_CHOICES, RECOMMENDED_COLORS, next_free_number
from views.color_dialog import get_color
from .panel_refresh import DeferredReportPanel

CATEGORY_LABELS = {"": "—", "steny": "Stěny", "podlahy": "Podlahy",
                   "strechy": "Střechy", "otvoroveVyplne": "Otvorové výplně"}


class MaterialColorDelegate(QStyledItemDelegate):
    """Keep the material swatch visible while the rest of its row is selected."""

    def paint(self, painter, option, index):
        swatch = QStyleOptionViewItem(option)
        swatch.state &= ~QStyle.State_Selected
        super().paint(painter, swatch, index)


class MaterialDialog(QDialog):
    def __init__(self, service, material=None, pids=None, parent=None):
        super().__init__(parent)
        self.service, self.material, self.pids = service, material, pids
        self.setWindowTitle("ArchControl — Upravit materiál" if material else "ArchControl — Nový materiál")
        self.resize(590, 620)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.typ = QComboBox()
        for key, label in TYPES:
            self.typ.addItem(f"{key} — {label}", key)
        form.addRow("Typ konstrukce", self.typ)
        number_row = QHBoxLayout()
        self.number = QSpinBox()
        self.number.setRange(1, 999999)
        number_row.addWidget(self.number)
        find = QPushButton("Najít volné")
        find.clicked.connect(self.find_number)
        number_row.addWidget(find)
        form.addRow("Číslo", number_row)
        self.variant = QComboBox()
        self.variant.addItems(["V1", "V2"])
        self.variant.setEditable(True)
        form.addRow("Varianta", self.variant)
        self.u = QLineEdit()
        self.u.setPlaceholderText("Neznámé U ponechte prázdné")
        form.addRow("U [W/(m²·K)]", self.u)
        self.un = QLabel()
        form.addRow("Požadavek Un", self.un)
        self.g = QLineEdit()
        self.g.setPlaceholderText("0,63")
        form.addRow("g", self.g)
        self.glazing = QComboBox()
        self.glazing.addItems(["", "S2", "S3"])
        form.addRow("Zasklení", self.glazing)
        self.description = QLineEdit()
        form.addRow("Popis konstrukce", self.description)
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self.choose_color)
        self.color = "#9e9e9e"
        self.base_color = QColor(self.color)
        form.addRow("Barva", self.color_button)
        self.shade = QSlider(Qt.Horizontal)
        self.shade.setRange(0, 100)
        self.shade.setValue(50)
        self.shade.setToolTip("0 = tmavá; 50 = základní barva; 100 = světlá")
        self.shade.valueChanged.connect(self.shade_color)
        form.addRow("Odstín", self.shade)
        self.apply = QCheckBox("Použít na vybrané plochy / skupiny")
        self.apply.setChecked(pids is not None)
        form.addRow(self.apply)
        self.info = QLabel()
        self.info.setWordWrap(True)
        form.addRow(self.info)
        layout.addLayout(form)
        rp_group = QGroupBox("Renovační pas (NZÚ)")
        rp_layout = QFormLayout(rp_group)
        self.rp = {}
        labels = ("Kategorie", "Typ RP", "Etapa", "Klient", "Lze zateplit")
        for field, label in zip(RP_FIELDS, labels):
            combo = QComboBox()
            combo.setMinimumWidth(160)
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            for value in RP_CHOICES[field]:
                combo.addItem(CATEGORY_LABELS.get(value, value or "—"), value)
            self.rp[field] = combo
            rp_layout.addRow(label, combo)
        self.rp["kategorie"].currentIndexChanged.connect(self.category_changed)
        self.rp["lze_zateplit"].currentIndexChanged.connect(self.insulation_changed)
        layout.addWidget(rp_group)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Uložit změny" if material else "Vytvořit materiál")
        buttons.button(QDialogButtonBox.Cancel).setText("Zrušit")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.typ.currentIndexChanged.connect(self.type_changed)
        if material:
            self.typ.setCurrentIndex(max(0, self.typ.findData(material["typ"])))
            self.number.setValue(int(material["cislo"] or 1))
            self.variant.setCurrentText(material["var"] or "V1")
            self.u.setText(material["u"])
            self.g.setText(material["g"])
            self.glazing.setCurrentText(material["sklo"])
            self.description.setText(material["popis"])
            self.set_color(material["color"])
            self.base_color = QColor(material["color"])
            for field, value in material["rp"].items():
                if field in self.rp:
                    combo = self.rp[field]
                    index = combo.findData(value)
                    if index < 0:
                        combo.addItem(value, value)
                        index = combo.count() - 1
                    combo.setCurrentIndex(index)
            self.type_changed(reset=False)
        else:
            self.find_number()
            self.type_changed()
        self.insulation_changed()

    def set_color(self, value):
        self.color = value
        self.color_button.setText(value)
        self.color_button.setStyleSheet(f"background-color: {value}; color: {'black' if QColor(value).lightness() > 128 else 'white'}")

    def choose_color(self):
        color = get_color(QColor(self.color), self, "Barva materiálu")
        if color.isValid():
            self.base_color = color
            self.shade.setValue(50)
            self.set_color(color.name())

    def shade_color(self, value):
        rgb = self.base_color.getRgb()[:3]
        channels = ([c * (.2 + .8 * value / 50) for c in rgb] if value <= 50 else
                    [c + (255 - c) * (.6 * (value - 50) / 50) for c in rgb])
        self.set_color(QColor(*[round(c) for c in channels]).name())

    def find_number(self):
        self.number.setValue(next_free_number([m["name"] for m in self.service.materials()], self.typ.currentData()))

    def type_changed(self, *_args, reset=True):
        typ = self.typ.currentData()
        normal = typ not in {"EP", "CV", "AB"}
        self.variant.setEnabled(normal)
        self.u.setEnabled(normal)
        self.un.setText(str(UN_VALUES.get(typ, "—")))
        self.g.setEnabled(typ in WINDOW_TYPES)
        self.glazing.setEnabled(typ in WINDOW_TYPES)
        self.info.setText("Adiabatická hranice nevstupuje do obálky ani do Energie CSV." if typ == "AB" else
                          "Typy STR5/SNT5 původní Ruby parser nerozpoznává. Jejich kompatibilita exportu není zaručena." if typ in {"STR5", "SNT5"} else "")
        if reset:
            self.base_color = QColor(*RECOMMENDED_COLORS.get(typ, RECOMMENDED_COLORS["_default"]))
            self.shade.setValue(50)
            self.set_color(self.base_color.name())
            if typ in WINDOW_TYPES and not self.g.text():
                self.g.setText("0.63")
            rp = read_rp(f"{typ}-1")
            for field in ("kategorie", "typ"):
                self.rp[field].setCurrentIndex(max(0, self.rp[field].findData(rp[field])))

    def category_changed(self, *_args):
        combo = self.rp["typ"]
        old = combo.currentData()
        combo.clear()
        combo.addItem("—", "")
        for value in RP_CATALOG["categories"].get(self.rp["kategorie"].currentData(), []):
            combo.addItem(value, value)
        combo.setCurrentIndex(max(0, combo.findData(old)))

    def insulation_changed(self, *_args):
        enabled = self.rp["lze_zateplit"].currentData() != "Ne"
        for field in ("etapa", "klient"):
            self.rp[field].setEnabled(enabled)

    def save(self):
        data = {"typ": self.typ.currentData(), "cislo": str(self.number.value()),
                "var": self.variant.currentText(), "u": self.u.text(), "g": self.g.text(),
                "sklo": self.glazing.currentText(), "popis": self.description.text(),
                "color": self.color, "apply": self.apply.isChecked(),
                "rp": {field: combo.currentData() for field, combo in self.rp.items()}}
        try:
            self.saved_name = self.service.save_material(data, self.material["name"] if self.material else None,
                                                        self.pids if self.apply.isChecked() else None)
        except (ValueError, OSError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class MaterialPalette(DeferredReportPanel):
    def __init__(self, service):
        super().__init__()
        self.service = service
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Název, typ, popis nebo zóna…")
        self.filter.textChanged.connect(self.refresh)
        filters.addWidget(self.filter)
        self.only_used = QCheckBox("Použité")
        self.only_used.toggled.connect(self.refresh)
        filters.addWidget(self.only_used)
        layout.addLayout(filters)
        buttons = QGridLayout()
        actions = [("Nový", self.new), ("Upravit", self.edit), ("Duplikovat", self.duplicate),
                   ("Použít na výběr", self.apply_selection), ("Skrýt / zobrazit", self.toggle_hidden),
                   ("Smazat", self.delete), ("Import JSON", self.import_library),
                   ("Export JSON", self.export_library), ("Obnovit", self.refresh),
                   ("Malovat materiálem", self.paint)]
        for i, (label, action) in enumerate(actions):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, callback=action: self.run(callback))
            buttons.addWidget(button, i // 3, i % 3)
        layout.addLayout(buttons)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["Materiál", "Typ", "U", "Un", "Plocha [m²]", "Zóny", "Barva", "Skrytý", "Akce"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setItemDelegateForColumn(6, MaterialColorDelegate(self.table))
        self.table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Fixed)
        self.table.setColumnWidth(8, 224)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 55), (2, 65), (3, 65), (4, 95), (5, 110), (6, 100), (7, 65)):
            self.table.setColumnWidth(column, width)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.cellDoubleClicked.connect(lambda *_: self.run(self.edit))
        layout.addWidget(self.table)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.refresh()

    def refresh(self, *_args):
        self._report_dirty = False
        selected = self.selected_name(required=False)
        needle = self.filter.text().casefold()
        rows = [r for r in self.service.materials() if (not self.only_used.isChecked() or r["area"] > 0)
                and needle in (r["name"] + " " + " ".join(r["zones"])).casefold()]
        display = tuple((r["name"], r["typ"], r["u"], r["un"], round(r["area"], 2),
                         tuple(r["zones"]), r["color"], r["hidden"]) for r in rows)
        if display == getattr(self, "_display_rows", None):
            return
        self._display_rows = display
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            values = (row["name"], row["typ"], row["u"], row["un"], row["area"],
                      ", ".join(row["zones"]), row["color"], "Ano" if row["hidden"] else "Ne")
            for j, value in enumerate(values):
                item = self.table.item(i, j)
                if item is None:
                    item = QTableWidgetItem()
                    self.table.setItem(i, j, item)
                item.setData(Qt.DisplayRole, round(value, 2) if isinstance(value, float) else str(value))
                if j == 0:
                    item.setToolTip(row["name"])
                if j == 6:
                    item.setBackground(QColor(row["color"]))
                    item.setForeground(QColor("black" if QColor(row["color"]).lightness() > 128 else "white"))
            actions = self.table.cellWidget(i, 8)
            if (actions is None or actions.property("material_name") != row["name"]
                    or actions.property("material_hidden") != row["hidden"]):
                self.table.setCellWidget(i, 8, self.row_actions(row))
            if row["name"] == selected:
                self.table.selectRow(i)
        self.table.setSortingEnabled(True)
        self.status.setText(f"Materiálů: {len(rows)}. Plochy započítávají obě strany a skrytou geometrii jako původní paleta.")

    def row_actions(self, material):
        from views.icons import tool_icon
        name = material["name"]
        widget = QWidget()
        widget.setProperty("material_name", name)
        widget.setProperty("material_hidden", material["hidden"])
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(3, 1, 3, 1)
        layout.setSpacing(2)
        actions = [("paint", "Malovat materiálem", self.paint),
                   ("select", "Použít na výběr", self.apply_selection),
                   ("line", "Upravit materiál", self.edit),
                   ("arr_duplicate", "Duplikovat materiál", self.duplicate),
                   (None, "Zobrazit" if material["hidden"] else "Skrýt", self.toggle_hidden),
                   ("eraser", "Smazat materiál", self.delete)]
        for key, label, callback in actions:
            button = QToolButton(widget)
            button.setToolTip(label)
            button.setAccessibleName(f"{label}: {name}")
            button.setProperty("material_action", label)
            button.setIconSize(QSize(20, 20))
            button.setFixedSize(28 if key else 66, 28)
            if key:
                button.setProperty("icon_key", key)
                button.setIcon(tool_icon(key))
            else:
                button.setText(label)
            button.clicked.connect(lambda _checked=False, n=name, fn=callback: self.run_row_action(n, fn))
            layout.addWidget(button)
        return widget

    def run_row_action(self, name, callback):
        # Bind to material identity, not its row number: sorting and filters
        # can move the button after it was created.
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text() == name:
                self.table.setCurrentCell(row, 0)
                self.table.selectRow(row)
                self.run(callback)
                return

    def selected_name(self, required=True):
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            if required:
                raise ValueError("Vyberte materiál v paletě.")
            return None
        return self.table.item(row, 0).text()

    def select_sampled_material(self, name):
        """Reveal a named material by identity, regardless of sort/filter state."""
        def find():
            return next((self.table.item(i, 0) for i in range(self.table.rowCount())
                         if self.table.item(i, 0).text() == name), None)
        if not name:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self.status.setText("Plocha nemá pojmenovaný materiál v knihovně modelu.")
            return False
        item = find()
        if item is None:
            with QSignalBlocker(self.filter), QSignalBlocker(self.only_used):
                self.filter.clear()
                self.only_used.setChecked(False)
            self.refresh()
            item = find()
        if item is None:
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self.status.setText(f"Materiál {name} není v knihovně modelu.")
            return False
        self.table.setCurrentItem(item)
        self.table.selectRow(item.row())
        self.table.scrollToItem(item, QAbstractItemView.PositionAtCenter)
        self.status.setText(f"Materiál z kapátka: {name}")
        return True

    def selected_material(self):
        name = self.selected_name()
        return next(r for r in self.service.materials() if r["name"] == name)

    def run(self, fn):
        try:
            fn()
        except (ValueError, OSError, KeyError) as exc:
            QMessageBox.warning(self, "ArchControl — materiály", str(exc))

    def new(self):
        MaterialDialog(self.service, parent=self).exec()
        self.refresh()

    def edit(self):
        material = self.selected_material()
        if material["typ"] not in dict(TYPES):
            raise ValueError("Materiál nemá rozpoznaný formát ArchControl. Vytvořte novou konstrukci a použijte ji na výběr.")
        MaterialDialog(self.service, material, parent=self).exec()
        self.refresh()

    def duplicate(self):
        self.service.duplicate_material(self.selected_name())
        self.refresh()

    def apply_selection(self):
        self.service.apply_material(self.selected_name())

    def paint(self):
        self.service.paint_material(self.selected_name())

    def toggle_hidden(self):
        self.service.toggle_material_hidden(self.selected_name())
        self.refresh()

    def delete(self):
        name = self.selected_name()
        if QMessageBox.question(self, "Smazat materiál", f"Smazat materiál {name}? Jeho plochy zůstanou bez tohoto materiálu.") == QMessageBox.Yes:
            self.service.delete_material(name)
            self.refresh()

    def import_library(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import knihovny materiálů", "", "JSON (*.json)")
        if path:
            count = self.service.import_library(path)
            self.refresh()
            self.status.setText(f"Importováno materiálů: {count}")

    def export_library(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export knihovny materiálů", "arch_control_materials.json", "JSON (*.json)")
        if path:
            self.service.export_library(path)
            self.status.setText("Knihovna uložena. Formát Ruby knihovny neobsahuje RP atributy ani textury.")
