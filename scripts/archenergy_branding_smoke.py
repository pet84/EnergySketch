# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Isolated profile + Czech standard buttons + offscreen About evidence."""
from pathlib import Path
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROFILE = tempfile.mkdtemp(prefix="energysketch-branding-")
os.environ["APPDATA"] = PROFILE
os.environ["XDG_DATA_HOME"] = PROFILE
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"))

from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel
from PySide6.QtGui import QIcon, QFont
from PySide6.QtCore import QSettings
from core.archenergy import configure_profile, user_data_dir, NOTICE

app = QApplication([])
configure_profile()
app.setFont(QFont("Segoe UI", 9))
app.setWindowIcon(QIcon(str(ROOT / "resources/icons/energysketch.ico")))
from main import _init_language
_init_language()
from core.i18n import current_language, tr
from core.paths import user_log_dir
from core.autosave import autosave_dir
from core.scale_figure import figures_dir
from core.extensions import user_plugins_dir
from core.texture import texture_cache_root
from core.render_blender import work_base
from georef.tiles import default_cache_dir
from views.composer import ComposerWindow
from views.about_dialog import AboutDialog

paths = {
    "settings": Path(QSettings().fileName()), "logs": user_log_dir(),
    "autosave": autosave_dir(), "figures": figures_dir(),
    "plugins": user_plugins_dir(), "textures": texture_cache_root(),
    "renders": work_base(), "tiles": default_cache_dir(),
    "sheet_templates": ComposerWindow.templates_dir(),
    "titleblock_templates": ComposerWindow.cajetin_templates_dir(),
}
for value in paths.values():
    assert value.is_relative_to(user_data_dir()), value
st = QSettings()
st.setValue("branding-smoke", "český profil")
st.sync()
assert st.status() == QSettings.NoError
assert Path(st.fileName()).is_file()
assert current_language() == "cs" and tr("File") == "Soubor"
buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Yes)
assert buttons.button(QDialogButtonBox.Cancel).text() == "Zrušit"
assert buttons.button(QDialogButtonBox.Yes).text().replace("&", "") == "Ano"
dlg = AboutDialog(None, "0.1-internal")
assert any(NOTICE in lab.text() for lab in dlg.findChildren(QLabel))
dlg.credits._timer.stop()
dlg.show()
app.processEvents()
out = ROOT / "output/archenergy"
assert dlg.grab().save(str(out / "energysketch-about-cs.png"))
report = {"ok": True, "language": current_language(),
          "title": dlg.windowTitle(), "notice": NOTICE,
          "paths": {k: str(v) for k, v in paths.items()},
          "cancel": buttons.button(QDialogButtonBox.Cancel).text(),
          "yes": buttons.button(QDialogButtonBox.Yes).text()}
(out / "energysketch-branding-smoke.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
dlg.close()
