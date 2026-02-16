from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Qt
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from app.ui import design_tokens as dt


class SegmentedNavBar(QWidget):
    def __init__(self, items: list[str], on_change: Callable[[int], None], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SegmentedNav")
        self._on_change = on_change
        self._buttons: list[QPushButton] = []
        self._active_index = 0

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(dt.SPACING_8)

        group = QButtonGroup(self)
        group.setExclusive(True)

        for idx, text in enumerate(items):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(44)
            btn.setMinimumWidth(120)
            btn.clicked.connect(lambda checked=False, i=idx: self._switch_to(i))
            group.addButton(btn, idx)
            row.addWidget(btn, 1)
            self._buttons.append(btn)

        if self._buttons:
            self._buttons[0].setChecked(True)

        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(120)
        self._fade.setStartValue(0.92)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def set_items(self, items: list[str]) -> None:
        for btn, text in zip(self._buttons, items):
            btn.setText(text)

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
            self._active_index = index

    def _switch_to(self, index: int) -> None:
        if index == self._active_index:
            return
        self._active_index = index
        self._fade.stop()
        self._fade.start()
        self._on_change(index)

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.end()
