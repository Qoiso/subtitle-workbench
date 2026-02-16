from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QLabel

from app.ui import design_tokens as dt


def make_form(parent=None) -> QFormLayout:
    form = QFormLayout(parent)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setHorizontalSpacing(dt.SPACING_16)
    form.setVerticalSpacing(dt.SPACING_12)
    return form


def apply_label_width(labels: Iterable[QLabel], width: int = dt.LABEL_WIDTH) -> None:
    for label in labels:
        label.setMinimumWidth(width)
        label.setMinimumHeight(24)
