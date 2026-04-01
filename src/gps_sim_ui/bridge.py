"""Мост QWebChannel для кликов по карте."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class MapBridge(QObject):
    """Вызывается из JavaScript при клике по карте."""

    pointClicked = Signal(float, float)

    @Slot(float, float)
    def reportClick(self, lat: float, lng: float) -> None:
        self.pointClicked.emit(lat, lng)
