from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from app.ui import design_tokens as dt


class PageShell(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(dt.SPACING_10, dt.SPACING_8, dt.SPACING_10, dt.SPACING_8)
        root.setSpacing(dt.SPACING_8)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.content = QWidget()
        self.content.setMaximumWidth(dt.CONTENT_MAX_WIDTH)

        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(dt.SPACING_4, dt.SPACING_4, dt.SPACING_4, dt.SPACING_12)
        self.body.setSpacing(dt.SPACING_12)

        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll, 1)

    def add_widget(self, widget: QWidget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)

    def add_stretch(self, stretch: int = 1) -> None:
        self.body.addStretch(stretch)

    def align_center(self) -> None:
        layout = self.layout()
        if isinstance(layout, QVBoxLayout):
            layout.setAlignment(self.scroll, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
