from __future__ import annotations

from PySide6.QtWidgets import QGroupBox


class SectionCard(QGroupBox):
    def __init__(self, title: str = "", parent=None) -> None:
        super().__init__(title, parent)
        self.setObjectName("SectionCard")
