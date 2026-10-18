# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Explicit user pairing; bearer tokens are never exposed to this widget."""
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)


class LivePanel(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>ASTRA · LIVE propojení</b>"))
        self.url = QLineEdit("https://app.archenergy.cz")
        self.url.setPlaceholderText("Adresa APP (HTTPS)")
        layout.addWidget(self.url)
        self.code = QLineEdit()
        self.code.setPlaceholderText("Jednorázový párovací kód z APP")
        self.code.setMaxLength(30)
        layout.addWidget(self.code)
        row = QHBoxLayout()
        self.connect_button = QPushButton("Připojit")
        self.connect_button.clicked.connect(self.connect_app)
        row.addWidget(self.connect_button)
        self.disconnect_button = QPushButton("Odpojit")
        self.disconnect_button.clicked.connect(controller.disconnect)
        row.addWidget(self.disconnect_button)
        self.pause_button = QPushButton("Pozastavit")
        self.pause_button.clicked.connect(controller.pause)
        row.addWidget(self.pause_button)
        layout.addLayout(row)
        self.connection = QLabel()
        layout.addWidget(self.connection)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.stats = QLabel()
        self.stats.setWordWrap(True)
        layout.addWidget(self.stats)
        info = QLabel("Podporuje LIVE náhled, testovací tělesa, import i adresné změny modelu APP "
                      "a přesun reportů EP/CP do podlaží. Token platí pouze pro tuto relaci a "
                      "neukládá se do souboru. Po změně dokumentu je nutné nové propojení.")
        info.setWordWrap(True)
        layout.addWidget(info)
        layout.addStretch()
        controller.updated.connect(self.update_status)
        self.update_status(controller.session.public_status())

    def connect_app(self):
        try:
            code = self.code.text()
            self.code.clear()
            self.controller.connect_app(self.url.text(), code)
        except ValueError as exc:
            QMessageBox.warning(self, "ASTRA LIVE", str(exc))

    def update_status(self, state):
        self.status.setText(state["status"])
        self.connection.setText({"online":"● Online", "offline":"○ Offline", "connecting":"◌ Připojování…"}[state["connectionStatus"]])
        stats = state["stats"]
        self.stats.setText(f"Potvrzená revize: {state['revision']} · dávky: {stats.get('batches',0)} · "
                           f"přeneseno: {stats.get('bytes',0)/1024:.1f} kB")
        self.pause_button.setText("Pokračovat" if state["paused"] else "Pozastavit")
        self.pause_button.setEnabled(state["connected"] and not state["needsPairing"])
        self.disconnect_button.setEnabled(state["connected"] or state["connectionStatus"] == "connecting")
