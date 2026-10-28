# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Render a proposed factory layout in an isolated profile and window."""
from pathlib import Path
import argparse
import json
import os
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
parser = argparse.ArgumentParser()
parser.add_argument('--state', type=Path)
parser.add_argument('--metadata', type=Path)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
os.environ['APPDATA'] = tempfile.mkdtemp(prefix='energy-layout-')
os.environ.pop('QT_QPA_PLATFORM', None)
from PySide6.QtCore import QByteArray, QSettings, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDockWidget, QToolBar
from core.archenergy import configure_profile
from main import _configure_surface_format, _init_language
from views.theme import apply_theme
from views.main_window import MainWindow

_configure_surface_format()
app = QApplication([])
configure_profile()
_init_language()
apply_theme(app)
settings = QSettings()
if args.state:
    settings.setValue('ui/window_state', QByteArray(args.state.read_bytes()))
    settings.remove('ui/energy_factory_pending')
if args.metadata:
    for key, value in json.loads(args.metadata.read_text(encoding='utf-8')).items():
        settings.setValue('ui/' + key, value)
window = MainWindow(defer_extensions=True)
window.setAttribute(Qt.WA_ShowWithoutActivating, True)
window.move(-32000,-32000)
window.resize(2256,1180)
result = {'ok':False}

def finish():
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.with_suffix('.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    window._saved_version = window.viewport.scene.version
    window.close()
    app.exit(0 if result['ok'] else 1)

def capture():
    try:
        assert not window._extension_load_errors, window._extension_load_errors
        result['bars'] = [dict(name=bar.objectName(),area=window.toolBarArea(bar).name,
                             x=bar.x(),y=bar.y(),width=bar.width(),height=bar.height(),
                             visible=bar.isVisibleTo(window),row_break=window.toolBarBreak(bar))
                          for bar in window.findChildren(QToolBar) if bar.parent() is window]
        result['docks'] = [dict(name=dock.objectName(),visible=dock.isVisibleTo(window),width=dock.width())
                           for dock in window.findChildren(QDockWidget)]
        assert window.grab().save(str(args.output))
        result['ok'] = True
    except Exception:
        import traceback
        result['error'] = traceback.format_exc()
    finish()

def load():
    window.load_extensions()
    QTimer.singleShot(800,capture)

window.show()
QTimer.singleShot(50,load)
QTimer.singleShot(30000,finish)
app.exec()
raise SystemExit(0 if result['ok'] else 1)
