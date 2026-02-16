from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.ui import design_tokens as dt


class LogDrawer(QWidget):
    def __init__(self, title: str, default_collapsed: bool = True, parent=None) -> None:
        super().__init__(parent)
        self._collapsed = default_collapsed

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(dt.SPACING_8)

        head = QWidget(self)
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(dt.SPACING_8)

        self.toggle_btn = QPushButton(title)
        self.toggle_btn.setObjectName("LogToggle")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(not default_collapsed)
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.clicked.connect(self.toggle)
        head_row.addWidget(self.toggle_btn, 0)
        head_row.addStretch(1)

        self.editor = QTextEdit(self)
        self.editor.setReadOnly(True)
        self.editor.setMinimumHeight(170)

        root.addWidget(head)
        root.addWidget(self.editor)
        self._apply_state()

    def _apply_state(self) -> None:
        self.editor.setVisible(not self._collapsed)

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        self.toggle_btn.setChecked(not self._collapsed)
        self._apply_state()

    def append_line(self, text: str) -> None:
        self.editor.append(text)

    def clear(self) -> None:
        self.editor.clear()

    @property
    def text_edit(self) -> QTextEdit:
        return self.editor
