# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Render native window/help dialogs and check a customer model in memory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="energysketch-windows-")
os.environ["QT_QPA_FONTDIR"] = str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts")
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from core.archenergy import configure_profile
from core.history import History
from plugins.archcontrol.adapter import PanelService, face_handles, face_records, parse_skp
from plugins.archcontrol.core import triangulated_area
from plugins.archcontrol.windows import Grid, window_material
from plugins.archcontrol.windows_ui import WindowGridDialog
from plugins.archcontrol.help_ui import HelpDialog
from views.main_window import MainWindow
from views.extension_api import ExtensionApp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", type=Path)
    args = ap.parse_args()
    before_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
    app = QApplication([])
    app.setFont(QFont("Segoe UI", 9))
    configure_profile()
    from main import _init_language
    _init_language()
    window = MainWindow(defer_extensions=True)
    scene = parse_skp(args.model)
    history = History(scene)
    window.viewport.scene, window.viewport.history = scene, history
    service = PanelService(ExtensionApp(window, "archcontrol"))
    dialog = WindowGridDialog(service, window)
    dialog.fields["cols"].setValue(3)
    dialog.fields["rows"].setValue(2)
    dialog.show()
    app.processEvents()
    out = ROOT / "output/archenergy"
    assert dialog.grab().save(str(out / "energysketch-window-grid-cs.png"))
    dialog.reject()
    help_dialog = HelpDialog(window)
    help_dialog.show()
    app.processEvents()
    assert "ArchControl pro EnergySketch" in help_dialog.browser.toPlainText()
    assert help_dialog.grab().save(str(out / "energysketch-help-cs.png"))
    help_dialog.close()
    records = list(face_records(scene))
    face = max((r for r in records if r.material.startswith("SO-") and r.visible),
               key=lambda r: triangulated_area(r.triangles))
    triangle = face.triangles[0]
    center = tuple(sum(p[i] for p in triangle)/3 for i in range(3))
    material = next(name for name in scene.materials if window_material(name))
    grid = Grid(width=.4, height=.4, material=material)
    before_area = sum(triangulated_area(r.triangles) for r in records)
    service.insert_window_grid(face.pid, center, grid)
    window.viewport.end_group_edit()
    after_area = sum(triangulated_area(r.triangles) for r in face_records(scene))
    assert history.undo()
    restored_area = sum(triangulated_area(r.triangles) for r in face_records(scene))
    assert abs(before_area-restored_area) < .0001
    assert hashlib.sha256(args.model.read_bytes()).hexdigest() == before_hash
    result = {"ok": True, "source_sha256": before_hash, "file_unchanged": True,
              "before_area_m2": before_area, "after_area_m2": after_area,
              "undo_area_m2": restored_area,
              "material": material, "native_grid_and_undo": True,
              "note": "Only a detached in-memory scene was changed; no model was saved."}
    (out / "reference-model-window-grid-smoke.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2))
    window._saved_version = scene.version
    window.close()


if __name__ == "__main__":
    main()
