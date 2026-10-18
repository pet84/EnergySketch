# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Keep report work out of hidden tabs and active camera gestures."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget


class DeferredReportPanel(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._report_dirty = False
        self._report_timer = QTimer(self)
        self._report_timer.setSingleShot(True)
        self._report_timer.timeout.connect(self._refresh_visible_report)

    def schedule_refresh(self, *_args):
        self._report_dirty = True
        if self._report_visible() and not self._report_timer.isActive():
            self._report_timer.start(0)

    def _report_visible(self):
        # Qt tabified docks remain isVisible() even when covered by another
        # tab. Their visibleRegion is empty until the tab is raised.
        return self.isVisible() and not self.visibleRegion().isEmpty()

    def bind_dock(self, dock):
        dock.visibilityChanged.connect(self._dock_visibility_changed)

    def _dock_visibility_changed(self, visible):
        if visible and self._report_dirty:
            self._report_timer.start(0)

    def _refresh_visible_report(self):
        if not self._report_visible() or not self._report_dirty:
            return
        viewport = getattr(getattr(self.service, "app", None), "viewport", None)
        if getattr(viewport, "_last_pos", None) is not None:
            self._report_timer.start(80)
            return
        self._report_dirty = False
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if self._report_dirty:
            self.schedule_refresh()
