# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Small branding and user-profile boundary for the internal distribution."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PRODUCT = "EnergySketch"
PUBLISHER = "ArchEnergy s.r.o."
WINDOW_NAME = f"{PRODUCT} · {PUBLISHER}"
NOTICE = ("EnergySketch je upravená verze programu IngeTrazo "
          "(© autoři IngeTrazo, GPL-3.0-or-later). "
          "Úpravy © 2026 ArchEnergy s.r.o.")


def user_data_dir() -> Path:
    """Independent of Qt application names, also usable before QApplication."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA")
                    or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME")
                    or Path.home() / ".local" / "share")
    return base / PRODUCT


def configure_profile() -> None:
    """Use one portable-to-backup INI under %APPDATA%/EnergySketch on Windows."""
    from PySide6.QtCore import QCoreApplication, QSettings
    QCoreApplication.setOrganizationName(PRODUCT)
    QCoreApplication.setApplicationName(PRODUCT)
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope,
                      str(user_data_dir().parent))
    # EnergySketch's first-run appearance. Seed only missing preferences:
    # later user choices and the upstream legacy keys remain authoritative.
    from . import general_settings
    settings = QSettings()
    for name, default in (("theme", "light"), ("accent", "blue")):
        if general_settings.value(name, settings=settings) is None:
            general_settings.set_value(name, default, settings=settings)
    if (settings.value("ui/toolbar_icon_px") is None
            and settings.value("ui/large_toolbar_icons") is None):
        settings.setValue("ui/toolbar_icon_px", 32)
