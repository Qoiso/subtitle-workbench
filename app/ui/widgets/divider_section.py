from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from app.ui import design_tokens as dt


class DividerSection(QWidget):
    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(dt.SPACING_8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("SectionTitle")
        self.divider = QFrame(self)
        self.divider.setFrameShape(QFrame.Shape.HLine)
        self.divider.setObjectName("SectionDivider")

        self.body = QWidget(self)

        root.addWidget(self.title_label)
        root.addWidget(self.divider)
        root.addWidget(self.body)

    def set_title(self, text: str) -> None:
        self.title_label.setText(text)
