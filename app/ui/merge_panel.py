from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.i18n import I18N
from app.core.models import MergeInput
from app.core.validator import Validator
from app.ui import design_tokens as dt
from app.ui.layout.form_grid import apply_label_width, make_form
from app.ui.widgets.action_row import ActionRow


class MergePanel(QWidget):
    def __init__(
        self,
        i18n: I18N,
        on_submit: Callable[[MergeInput], None],
        on_cancel: Callable[[], None],
        on_pause_toggle: Callable[[], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self._on_pause_toggle = on_pause_toggle
        self._video_paths: list[str] = []
        self._image_paths: list[str] = []
        self._audio_paths: list[str] = []
        self._subtitle_paths: list[str] = []
        self._build_ui()
        self.i18n.subscribe(self.retranslate_ui)
        self.retranslate_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(dt.SPACING_8)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(8)
        root.addWidget(splitter, 1)

        left = QWidget(self)
        left.setObjectName("OpsPane")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 6, 8, 6)
        left_layout.setSpacing(dt.SPACING_8)

        input_box = QFrame(left)
        input_box.setObjectName("PanelGroup")
        input_layout = QVBoxLayout(input_box)
        input_layout.setContentsMargins(10, 10, 10, 10)
        input_layout.setSpacing(dt.SPACING_8)
        self.input_title = QLabel("")
        self.input_title.setObjectName("GroupTitle")
        input_layout.addWidget(self.input_title)
        input_form = make_form()

        self.video_label = QLabel("-")
        self.image_label = QLabel("-")
        self.audio_label = QLabel("-")
        self.subtitle_label = QLabel("-")

        self.video_pick_btn = QPushButton()
        self.video_pick_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.video_pick_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.video_pick_btn.clicked.connect(self._pick_video)
        self.image_pick_btn = QPushButton()
        self.image_pick_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.image_pick_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.image_pick_btn.clicked.connect(self._pick_image)
        self.audio_pick_btn = QPushButton()
        self.audio_pick_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.audio_pick_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.audio_pick_btn.clicked.connect(self._pick_audio)
        self.subtitle_pick_btn = QPushButton()
        self.subtitle_pick_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.subtitle_pick_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.subtitle_pick_btn.clicked.connect(self._pick_subtitle)

        self.video_row = self._picker_row(self.video_label, self.video_pick_btn)
        self.image_row = self._picker_row(self.image_label, self.image_pick_btn)
        self.audio_row = self._picker_row(self.audio_label, self.audio_pick_btn)
        self.subtitle_row = self._picker_row(self.subtitle_label, self.subtitle_pick_btn)

        self.output_edit = QLineEdit()
        self.output_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.output_btn = QPushButton()
        self.output_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.output_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.output_btn.clicked.connect(self._pick_output)
        output_wrap = QWidget()
        output_layout = QHBoxLayout(output_wrap)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(dt.SPACING_8)
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(self.output_btn)

        self.video_title = self._with_help("", "仅视频格式")
        self.image_title = QLabel("")
        self.audio_title = QLabel("")
        self.subtitle_title = QLabel("")
        self.output_title = QLabel("")

        input_form.addRow(self.video_title, self.video_row)
        input_form.addRow(self.image_title, self.image_row)
        input_form.addRow(self.audio_title, self.audio_row)
        input_form.addRow(self.subtitle_title, self.subtitle_row)
        input_form.addRow(self.output_title, output_wrap)
        apply_label_width((input_form.labelForField(self.video_row), self.image_title, self.audio_title, self.subtitle_title, self.output_title))
        input_layout.addLayout(input_form)

        options_box = QFrame(left)
        options_box.setObjectName("PanelGroup")
        options_layout = QVBoxLayout(options_box)
        options_layout.setContentsMargins(10, 10, 10, 10)
        options_layout.setSpacing(dt.SPACING_8)
        self.options_title = QLabel("")
        self.options_title.setObjectName("GroupTitle")
        options_layout.addWidget(self.options_title)
        options_form = make_form()

        self.container_combo = QComboBox()
        self.container_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.container_combo.addItems(["mkv", "mp4"])

        self.encode_combo = QComboBox()
        self.encode_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.encode_combo.addItem("", "cpu_h264")
        self.encode_combo.addItem("", "nvidia_h265")
        self.encode_combo.addItem("", "lossless_copy")

        self.sync_combo = QComboBox()
        self.sync_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.sync_combo.addItems(["longest", "shortest", "video", "audio"])

        self.subtitle_mode_combo = QComboBox()
        self.subtitle_mode_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.subtitle_mode_combo.addItem("", "soft")
        self.subtitle_mode_combo.addItem("", "hard")
        self.subtitle_mode_combo.currentIndexChanged.connect(self._refresh_lossless_availability)

        self.container_title = QLabel("")
        self.encode_title = QLabel("")
        self.subtitle_mode_title = QLabel("")
        self.sync_title = self._with_help("", "longest 推荐：以最长轨道为准；shortest 会裁切到最短轨道。")

        options_form.addRow(self.container_title, self.container_combo)
        options_form.addRow(self.encode_title, self.encode_combo)
        options_form.addRow(self.subtitle_mode_title, self.subtitle_mode_combo)
        options_form.addRow(self.sync_title, self.sync_combo)
        apply_label_width((self.container_title, self.encode_title, self.subtitle_mode_title, options_form.labelForField(self.sync_combo)))
        options_layout.addLayout(options_form)

        exec_box = QFrame(left)
        exec_box.setObjectName("PanelGroup")
        exec_layout = QVBoxLayout(exec_box)
        exec_layout.setContentsMargins(10, 10, 10, 10)
        exec_layout.setSpacing(dt.SPACING_8)
        self.exec_title = QLabel("")
        self.exec_title.setObjectName("GroupTitle")
        exec_layout.addWidget(self.exec_title)
        exec_form = make_form()

        self.submit_btn = QPushButton()
        self.submit_btn.clicked.connect(self._submit)
        self.cancel_btn = QPushButton()
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.pause_btn = QPushButton()
        self.pause_btn.clicked.connect(self._on_pause_toggle)
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._clear_log)
        actions = ActionRow((self.submit_btn, self.cancel_btn, self.pause_btn, self.clear_btn))

        exec_layout.addLayout(exec_form)
        exec_layout.addWidget(actions)

        left_layout.addWidget(input_box)
        left_layout.addWidget(options_box)
        left_layout.addWidget(exec_box)
        left_layout.addStretch(1)

        right = QWidget(self)
        right.setObjectName("LogPane")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 8, 10, 8)
        right_layout.setSpacing(dt.SPACING_8)
        right.setMinimumWidth(410)
        right.setMaximumWidth(460)
        self.log_progress_title = QLabel("")
        self.log_progress_title.setObjectName("GroupTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(320)
        right_layout.addWidget(self.log_progress_title)
        right_layout.addWidget(self.progress)
        right_layout.addWidget(self.log_text, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([860, 430])

    def retranslate_ui(self) -> None:
        self.input_title.setText(self.i18n.t("merge.section.input"))
        self.options_title.setText(self.i18n.t("merge.section.options"))
        self.exec_title.setText(self.i18n.t("merge.section.execute"))
        self.video_title.layout().itemAt(0).widget().setText(self.i18n.t("merge.video"))
        self.image_title.setText(self.i18n.t("merge.image"))
        self.audio_title.setText(self.i18n.t("merge.audio"))
        self.subtitle_title.setText(self.i18n.t("merge.subtitle"))
        self.output_title.setText(self.i18n.t("merge.output_file"))
        self.container_title.setText(self.i18n.t("merge.output_format"))
        self.encode_title.setText(self.i18n.t("merge.priority"))
        self.subtitle_mode_title.setText(self.i18n.t("merge.subtitle_mode"))
        self.sync_title.layout().itemAt(0).widget().setText(self.i18n.t("merge.sync_mode"))
        self.log_progress_title.setText(self.i18n.t("merge.progress"))
        self.video_pick_btn.setText(self.i18n.t("common.select"))
        self.image_pick_btn.setText(self.i18n.t("common.select"))
        self.audio_pick_btn.setText(self.i18n.t("common.select"))
        self.subtitle_pick_btn.setText(self.i18n.t("common.select"))
        self.output_btn.setText(self.i18n.t("common.select"))
        self.encode_combo.setItemText(0, self.i18n.t("merge.priority.cpu_h264"))
        self.encode_combo.setItemText(1, self.i18n.t("merge.priority.nvidia_h265"))
        self.encode_combo.setItemText(2, self.i18n.t("merge.priority.lossless_copy"))
        self.subtitle_mode_combo.setItemText(0, self.i18n.t("merge.subtitle_mode.soft"))
        self.subtitle_mode_combo.setItemText(1, self.i18n.t("merge.subtitle_mode.hard"))
        self.submit_btn.setText(self.i18n.t("merge.start"))
        self.cancel_btn.setText(self.i18n.t("common.cancel_task"))
        if self.pause_btn.text() not in {self.i18n.t("common.pause_task"), self.i18n.t("common.resume_task")}:
            self.pause_btn.setText(self.i18n.t("common.pause_task"))
        self.clear_btn.setText(self.i18n.t("common.clear"))
        self._refresh_lossless_availability()
        self.set_task_state("idle")

    def _with_help(self, text: str, tooltip: str) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(dt.SPACING_8)
        title = QLabel(text)
        title.setStyleSheet("font-weight:600;")
        badge = QLabel("?")
        badge.setToolTip(tooltip)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(18, 18)
        badge.setStyleSheet("QLabel {font-weight:700;font-size:12px;color:#059669;border:1px solid #059669;border-radius:9px;background:rgba(255,255,255,0.92);}")
        row.addWidget(title)
        row.addWidget(badge)
        row.addStretch(1)
        return wrap

    @staticmethod
    def _picker_row(label: QLabel, btn: QPushButton) -> QWidget:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(dt.SPACING_8)
        row.addWidget(label, 1)
        row.addWidget(btn)
        wrap = QWidget()
        wrap.setLayout(row)
        return wrap

    def _pick_video(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self.i18n.t("merge.video"), "", "Video (*.mp4 *.mkv *.mov *.avi *.flv *.webm *.m4v)")
        self._video_paths = files
        self._update_path_label(self.video_label, files)

    def _pick_image(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self.i18n.t("merge.image"), "", "Image (*.png *.jpg *.jpeg *.bmp *.webp)")
        self._image_paths = files
        self._update_path_label(self.image_label, files)
        self._refresh_lossless_availability()

    def _pick_audio(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self.i18n.t("merge.audio"), "", "Audio (*.mp3 *.aac *.m4a *.wav *.flac *.ogg)")
        self._audio_paths = files
        self._update_path_label(self.audio_label, files)

    def _pick_subtitle(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, self.i18n.t("merge.subtitle"), "", "Subtitle (*.srt *.ass *.ssa *.vtt *.sub)")
        self._subtitle_paths = files
        self._update_path_label(self.subtitle_label, files)

    def _pick_output(self) -> None:
        container = self.container_combo.currentText()
        path, _ = QFileDialog.getSaveFileName(self, self.i18n.t("merge.output_file"), "", f"{container.upper()} (*.{container})")
        if path:
            self.output_edit.setText(path)

    @staticmethod
    def _update_path_label(label: QLabel, paths: list[str]) -> None:
        label.setText(f"{len(paths)} files" if paths else "-")
        label.setToolTip("\n".join(paths) if paths else "")

    def _submit(self) -> None:
        payload = MergeInput(
            visual_paths=self._video_paths,
            audio_paths=self._audio_paths,
            subtitle_paths=self._subtitle_paths,
            output_path=self.output_edit.text().strip(),
            image_paths=self._image_paths,
            output_quality=str(self.encode_combo.currentData() or "cpu_h264"),
            subtitle_mode=str(self.subtitle_mode_combo.currentData() or "soft"),
            output_container=self.container_combo.currentText(),
            sync_mode=self.sync_combo.currentText(),
        )
        valid = Validator.validate_merge_input(payload)
        if not valid.ok:
            QMessageBox.warning(self, "Error", valid.message)
            return
        self._on_submit(payload)

    def append_log(self, line: str) -> None:
        self.log_text.append(line)

    def _clear_log(self) -> None:
        self.log_text.clear()
        self.progress.setValue(0)

    def set_progress(self, percent: float, message: str = "") -> None:
        self.progress.setValue(int(max(0, min(100, percent))))
        if message:
            self.append_log(message)

    def clear_inputs_after_success(self) -> None:
        self._video_paths = []
        self._image_paths = []
        self._audio_paths = []
        self._subtitle_paths = []
        self._update_path_label(self.video_label, [])
        self._update_path_label(self.image_label, [])
        self._update_path_label(self.audio_label, [])
        self._update_path_label(self.subtitle_label, [])
        self.output_edit.clear()
        self.progress.setValue(0)
        self._refresh_lossless_availability()
        self.pause_btn.setText(self.i18n.t("common.pause_task"))
        self.set_task_state("idle")

    def _refresh_lossless_availability(self) -> None:
        lossless_idx = self.encode_combo.findData("lossless_copy")
        if lossless_idx < 0:
            return
        block_lossless = bool(self._image_paths) or str(self.subtitle_mode_combo.currentData() or "soft") == "hard"

        model = self.encode_combo.model()
        item = getattr(model, "item", lambda *_: None)(lossless_idx)
        if item is not None:
            item.setEnabled(not block_lossless)

        if block_lossless and self.encode_combo.currentIndex() == lossless_idx:
            self.encode_combo.setCurrentIndex(0)
        if block_lossless:
            self.encode_combo.setToolTip(self.i18n.t("merge.lossless_blocked"))
        else:
            self.encode_combo.setToolTip("")

    def set_task_state(self, state: str) -> None:
        _ = state

    def export_state(self) -> dict[str, object]:
        return {
            "video_paths": list(self._video_paths),
            "image_paths": list(self._image_paths),
            "audio_paths": list(self._audio_paths),
            "subtitle_paths": list(self._subtitle_paths),
            "output_path": self.output_edit.text().strip(),
            "output_container": self.container_combo.currentText(),
            "output_quality": str(self.encode_combo.currentData() or "cpu_h264"),
            "subtitle_mode": str(self.subtitle_mode_combo.currentData() or "soft"),
            "sync_mode": self.sync_combo.currentText(),
        }

    def apply_saved_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return
        self._video_paths = [str(p) for p in state.get("video_paths", []) if isinstance(p, str) and Path(p).exists()]
        self._image_paths = [str(p) for p in state.get("image_paths", []) if isinstance(p, str) and Path(p).exists()]
        self._audio_paths = [str(p) for p in state.get("audio_paths", []) if isinstance(p, str) and Path(p).exists()]
        self._subtitle_paths = [str(p) for p in state.get("subtitle_paths", []) if isinstance(p, str) and Path(p).exists()]
        self._update_path_label(self.video_label, self._video_paths)
        self._update_path_label(self.image_label, self._image_paths)
        self._update_path_label(self.audio_label, self._audio_paths)
        self._update_path_label(self.subtitle_label, self._subtitle_paths)

        out_path = str(state.get("output_path", "") or "").strip()
        if out_path:
            self.output_edit.setText(out_path)

        container = str(state.get("output_container", "") or "")
        c_idx = self.container_combo.findText(container)
        if c_idx >= 0:
            self.container_combo.setCurrentIndex(c_idx)

        quality = str(state.get("output_quality", "") or "")
        q_idx = self.encode_combo.findData(quality)
        if q_idx >= 0:
            self.encode_combo.setCurrentIndex(q_idx)

        sub_mode = str(state.get("subtitle_mode", "") or "")
        s_idx = self.subtitle_mode_combo.findData(sub_mode)
        if s_idx >= 0:
            self.subtitle_mode_combo.setCurrentIndex(s_idx)

        sync_mode = str(state.get("sync_mode", "") or "")
        m_idx = self.sync_combo.findText(sync_mode)
        if m_idx >= 0:
            self.sync_combo.setCurrentIndex(m_idx)

        self._refresh_lossless_availability()
