from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QHBoxLayout,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.i18n import I18N
from app.core.models import DownloadInput
from app.ui import design_tokens as dt
from app.ui.layout.form_grid import apply_label_width, make_form
from app.ui.widgets.action_row import ActionRow


class DownloadPanel(QWidget):
    def __init__(
        self,
        i18n: I18N,
        on_fetch_formats: Callable[[DownloadInput], None],
        on_download: Callable[[DownloadInput], None],
        on_cancel: Callable[[], None],
        on_pause_toggle: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._on_fetch_formats = on_fetch_formats
        self._on_download = on_download
        self._on_cancel = on_cancel
        self._on_pause_toggle = on_pause_toggle
        self._build_ui()
        self.i18n.subscribe(self.retranslate_ui)
        self.retranslate_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(dt.SPACING_8)

        splitter = QSplitter(self)
        splitter.setOrientation(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        root.addWidget(splitter, 1)

        left = QWidget(self)
        left.setObjectName("OpsPane")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 6, 8, 6)
        left_layout.setSpacing(dt.SPACING_8)

        url_box = QFrame(left)
        url_box.setObjectName("PanelGroup")
        url_box_layout = QVBoxLayout(url_box)
        url_box_layout.setContentsMargins(10, 10, 10, 10)
        self.url_title = QLabel("")
        self.url_title.setObjectName("GroupTitle")
        url_box_layout.addWidget(self.url_title)
        url_form = make_form()

        self.url_label = QLabel("")
        self.url_edit = QLineEdit()
        self.url_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.url_edit.setPlaceholderText("https://...")

        self.output_label = QLabel("")
        self.output_edit = QLineEdit()
        self.output_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.pick_output_btn = QPushButton()
        self.pick_output_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.pick_output_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.pick_output_btn.clicked.connect(self._pick_output)
        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(dt.SPACING_8)
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(self.pick_output_btn)

        url_form.addRow(self.url_label, self.url_edit)
        url_form.addRow(self.output_label, output_row)
        apply_label_width((self.url_label, self.output_label))
        url_box_layout.addLayout(url_form)

        cookie_box = QFrame(left)
        cookie_box.setObjectName("PanelGroup")
        cookie_box_layout = QVBoxLayout(cookie_box)
        cookie_box_layout.setContentsMargins(10, 10, 10, 10)
        self.cookie_title = QLabel("")
        self.cookie_title.setObjectName("GroupTitle")
        cookie_box_layout.addWidget(self.cookie_title)
        cookie_form = make_form()

        self.cookie_mode_label = QLabel("")
        self.cookies_mode = QComboBox()
        self.cookies_mode.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.cookies_mode.addItems(["none", "file", "browser"])

        self.browser_label = QLabel("")
        self.browser_combo = QComboBox()
        self.browser_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.browser_combo.addItems(["chrome", "edge", "firefox"])

        self.cookie_file_label = QLabel("")
        self.cookie_file_edit = QLineEdit()
        self.cookie_file_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.pick_cookie_btn = QPushButton()
        self.pick_cookie_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.pick_cookie_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.pick_cookie_btn.clicked.connect(self._pick_cookie)
        cookie_row = QWidget()
        cookie_row_layout = QHBoxLayout(cookie_row)
        cookie_row_layout.setContentsMargins(0, 0, 0, 0)
        cookie_row_layout.setSpacing(dt.SPACING_8)
        cookie_row_layout.addWidget(self.cookie_file_edit, 1)
        cookie_row_layout.addWidget(self.pick_cookie_btn)

        cookie_form.addRow(self.cookie_mode_label, self.cookies_mode)
        cookie_form.addRow(self.browser_label, self.browser_combo)
        cookie_form.addRow(self.cookie_file_label, cookie_row)
        apply_label_width((self.cookie_mode_label, self.browser_label, self.cookie_file_label))
        cookie_box_layout.addLayout(cookie_form)

        exec_box = QFrame(left)
        exec_box.setObjectName("PanelGroup")
        exec_box_layout = QVBoxLayout(exec_box)
        exec_box_layout.setContentsMargins(10, 10, 10, 10)
        self.exec_title = QLabel("")
        self.exec_title.setObjectName("GroupTitle")
        exec_box_layout.addWidget(self.exec_title)
        exec_form = make_form()

        self.quality_label = QLabel("")
        self.format_combo = QComboBox()
        self.format_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.format_combo.addItem(self.i18n.t("download.best_auto"), "bestvideo+bestaudio/best")

        self.fetch_btn = QPushButton()
        self.fetch_btn.clicked.connect(self._fetch_formats)
        self.download_btn = QPushButton()
        self.download_btn.clicked.connect(self._download)
        self.cancel_btn = QPushButton()
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(self._on_pause_toggle)
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._clear_log)
        actions = ActionRow((self.fetch_btn, self.download_btn, self.cancel_btn, self.pause_btn, self.clear_btn))

        exec_form.addRow(self.quality_label, self.format_combo)
        apply_label_width((self.quality_label,))
        exec_box_layout.addLayout(exec_form)
        exec_box_layout.addWidget(actions)

        left_layout.addWidget(url_box)
        left_layout.addWidget(cookie_box)
        left_layout.addWidget(exec_box)
        left_layout.addStretch(1)

        right = QWidget(self)
        right.setObjectName("LogPane")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 8, 10, 8)
        right_layout.setSpacing(dt.SPACING_8)
        right.setMinimumWidth(410)
        right.setMaximumWidth(460)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("GroupTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(320)
        right_layout.addWidget(self.progress_label)
        right_layout.addWidget(self.progress)
        right_layout.addWidget(self.log_text, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([860, 430])

    def retranslate_ui(self) -> None:
        self.url_title.setText(self.i18n.t("download.section.basic"))
        self.cookie_title.setText(self.i18n.t("download.section.cookie"))
        self.exec_title.setText(self.i18n.t("download.section.execute"))
        self.url_label.setText(self.i18n.t("download.url"))
        self.output_label.setText(self.i18n.t("download.output_dir"))
        self.cookie_mode_label.setText(self.i18n.t("download.cookie_mode"))
        self.browser_label.setText(self.i18n.t("download.browser"))
        self.cookie_file_label.setText(self.i18n.t("download.cookie_file"))
        self.quality_label.setText(self.i18n.t("download.quality"))
        self.progress_label.setText(self.i18n.t("download.progress"))
        self.pick_output_btn.setText(self.i18n.t("common.select"))
        self.pick_cookie_btn.setText(self.i18n.t("common.select"))
        self.fetch_btn.setText(self.i18n.t("download.fetch_quality"))
        self.download_btn.setText(self.i18n.t("download.start"))
        self.cancel_btn.setText(self.i18n.t("common.cancel_task"))
        if self.pause_btn.text() not in {self.i18n.t("common.pause_task"), self.i18n.t("common.resume_task")}:
            self.pause_btn.setText(self.i18n.t("common.pause_task"))
        self.clear_btn.setText(self.i18n.t("common.clear"))
        if self.format_combo.count() > 0 and str(self.format_combo.itemData(0) or "") == "bestvideo+bestaudio/best":
            self.format_combo.setItemText(0, self.i18n.t("download.best_auto"))

    def _pick_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.i18n.t("download.output_dir"))
        if path:
            self.output_edit.setText(path)

    def _pick_cookie(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.i18n.t("download.cookie_file"), "", "Text (*.txt)")
        if path:
            self.cookie_file_edit.setText(path)

    def _build_payload(self) -> DownloadInput | None:
        url = self.url_edit.text().strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            QMessageBox.warning(self, "URL", "Only http/https URL is supported.")
            return None
        output_dir = self.output_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "Path", "Please choose output directory.")
            return None
        return DownloadInput(
            url=url,
            output_dir=output_dir,
            format_selector=str(self.format_combo.currentData() or self.format_combo.currentText()),
            cookies_mode=self.cookies_mode.currentText(),
            cookies_file=self.cookie_file_edit.text().strip() or None,
            browser_name=self.browser_combo.currentText() or None,
        )

    def _fetch_formats(self) -> None:
        payload = self._build_payload()
        if payload:
            self._on_fetch_formats(payload)

    def _download(self) -> None:
        payload = self._build_payload()
        if payload:
            self._on_download(payload)

    def set_formats(self, values: list[dict[str, Any]]) -> None:
        self.format_combo.clear()
        if not values:
            self.format_combo.addItem(self.i18n.t("download.best_auto"), "bestvideo+bestaudio/best")
            return
        for item in values:
            self.format_combo.addItem(item.get("label", ""), item.get("value", ""))

    def set_progress(self, percent: float, message: str = "") -> None:
        self.progress.setValue(int(max(0, min(100, percent))))

    def append_log(self, line: str) -> None:
        self.set_live_log(line)

    def set_live_log(self, line: str) -> None:
        text = " ".join(str(line).replace("\r", " ").replace("\n", " ").split())
        self.log_text.setPlainText(text)

    def _clear_log(self) -> None:
        self.log_text.clear()
        self.progress.setValue(0)

    def apply_defaults(self, output_dir: str, cookie_mode: str, browser: str) -> None:
        if output_dir:
            self.output_edit.setText(output_dir)
        mode_idx = self.cookies_mode.findText(cookie_mode)
        if mode_idx >= 0:
            self.cookies_mode.setCurrentIndex(mode_idx)
        browser_idx = self.browser_combo.findText(browser)
        if browser_idx >= 0:
            self.browser_combo.setCurrentIndex(browser_idx)

    def set_pause_state(self, paused: bool) -> None:
        self.pause_btn.setText(self.i18n.t("common.resume_task") if paused else self.i18n.t("common.pause_task"))

    def export_state(self) -> dict[str, object]:
        return {
            "url": self.url_edit.text().strip(),
            "output_dir": self.output_edit.text().strip(),
            "cookie_mode": self.cookies_mode.currentText(),
            "browser": self.browser_combo.currentText(),
            "cookie_file": self.cookie_file_edit.text().strip(),
            "format_value": str(self.format_combo.currentData() or self.format_combo.currentText()),
        }

    def apply_saved_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return
        url = str(state.get("url", "") or "").strip()
        if url:
            self.url_edit.setText(url)
        out_dir = str(state.get("output_dir", "") or "").strip()
        if out_dir:
            self.output_edit.setText(out_dir)
        cookie_mode = str(state.get("cookie_mode", "") or "")
        m_idx = self.cookies_mode.findText(cookie_mode)
        if m_idx >= 0:
            self.cookies_mode.setCurrentIndex(m_idx)
        browser = str(state.get("browser", "") or "")
        b_idx = self.browser_combo.findText(browser)
        if b_idx >= 0:
            self.browser_combo.setCurrentIndex(b_idx)
        cookie_file = str(state.get("cookie_file", "") or "").strip()
        if cookie_file:
            self.cookie_file_edit.setText(cookie_file)
        fmt = str(state.get("format_value", "") or "")
        if fmt:
            idx = self.format_combo.findData(fmt)
            if idx >= 0:
                self.format_combo.setCurrentIndex(idx)
            elif fmt and fmt != "bestvideo+bestaudio/best":
                self.format_combo.addItem(fmt, fmt)
                self.format_combo.setCurrentIndex(self.format_combo.count() - 1)
