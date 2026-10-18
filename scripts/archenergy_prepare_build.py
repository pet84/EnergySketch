# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Derive a separate Windows build spec without editing upstream packaging."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = (ROOT / "ingetrazo.spec").read_text(encoding="utf-8")
    spec = spec.split("# ── macOS: wrap the onedir COLLECT", 1)[0]
    changes = [
        ("['main.py']", "['energysketch.py']", 1),
        ("name='ingetrazo',", "name='EnergySketch',", 2),
        ("name='ingetrazo-mcp',", "name='EnergySketch-mcp',", 1),
        ("/ 'ingetrazo.ico'", "/ 'energysketch.ico'", 1),
        ("icon=icon,\n)", "icon=icon,\n    version=str(ROOT / 'packaging/energysketch-version.txt'),\n)", 1),
        ("icon=icon,\n)", "icon=icon,\n    version=str(ROOT / 'packaging/energysketch-mcp-version.txt'),\n)", 1),
        ("[*Path('plugins').glob('*.py'),", "[*Path('plugins').rglob('*.py'),", 1),
        ("collect_data_files('openskp')", "collect_data_files('openskp', include_py_files=True)", 1),
    ]
    for old, new, count in changes:
        if spec.count(old) < count:
            raise ValueError(f"Upstream build changed: missing {old!r}")
        spec = spec.replace(old, new, count)
    extra = '''
# ArchEnergy: the plugin is a package discovered by path, including offline help.
datas += [('LICENSE', '.'), ('AUTHORS', '.'), ('NOTICE', '.'), ('ARCHENERGY.md', '.')]
datas += [('docs/ENERGYSKETCH_AIRIS.md', 'docs')]
datas += [('resources/icons/energysketch-logo.svg', 'resources/icons'),
          ('resources/icons/energysketch-logo-dark.svg', 'resources/icons')]
for _source in Path('plugins/archcontrol').rglob('*'):
    if _source.is_file() and '__pycache__' not in _source.parts:
        datas.append((str(_source), str(_source.parent)))
hiddenimports += collect_submodules('plugins.archcontrol')
# The private reader loads physical .py files; do not bundle the writer scaffold.
from PySide6.QtCore import QLibraryInfo
_qt_translations = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
datas += [(str(_qt_translations / 'qtbase_cs.qm'), 'PySide6/translations')]
# Dependency license notices travel with the internal distribution.
from importlib import metadata
for _dependency in ('PySide6', 'PySide6-Essentials', 'PySide6-Addons', 'shiboken6',
                    'numpy', 'openskp', 'ezdxf', 'manifold3d', 'mapbox-earcut'):
    _dist = metadata.distribution(_dependency)
    for _file in _dist.files or ():
        if ('license' in str(_file).lower() or 'copying' in str(_file).lower()) and str(_file).lower().endswith(('.txt', '.md', 'license', 'copying')):
            _source = Path(_dist.locate_file(_file))
            if _source.is_file():
                datas.append((str(_source), 'licenses/' + _dependency))
'''
    marker = "a = Analysis("
    if spec.count(marker) != 2:  # GUI and mcp_a contain this suffix
        raise ValueError("Unexpected upstream Analysis structure")
    spec = spec.replace(marker, extra + "\n" + marker, 1)
    marker = "pyz = PYZ(a.pure, a.zipped_data)"
    if spec.count(marker) != 1:
        raise ValueError("Upstream PYZ structure changed")
    spec = spec.replace(marker, '''# Qt 6.11 Windows imports the OS ICU ABI. A Poppler ICU on the build
# host's PATH has the same DLL name but versioned exports; bundling it makes
# QtWidgets fail with ERROR_PROC_NOT_FOUND. Use Windows' own ICU, as the wheel does.
if sys.platform == 'win32':
    a.binaries = [b for b in a.binaries
                  if Path(b[0]).name.lower() not in {'icuuc.dll', 'icudt78.dll'}]

''' + marker, 1)
    spec = ("# SPDX-License-Identifier: GPL-3.0-or-later\n"
            "# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.\n"
            "# Modifications © 2026 ArchEnergy s.r.o.\n" + spec)
    (ROOT / "EnergySketch.spec").write_text(spec, encoding="utf-8", newline="\n")
    print("EnergySketch.spec ready; upstream ingetrazo.spec unchanged")


if __name__ == "__main__":
    main()
