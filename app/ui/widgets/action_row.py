from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from app.ui import design_tokens as dt


class ActionRow(QWidget):
    def __init__(self, buttons: Iterable[QPushButton], parent=None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(dt.SPACING_8)
        for btn in buttons:
            btn.setMinimumWidth(0)
            btn.setMinimumHeight(dt.BUTTON_HEIGHT)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row.addWidget(btn, 1)
