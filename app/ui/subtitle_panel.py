from __future__ import annotations

import json
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.i18n import I18N
from app.core.models import SubtitleJobInput
from app.ui import design_tokens as dt
from app.ui.layout.form_grid import apply_label_width, make_form


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event) -> None:  # noqa: N802
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        event.ignore()


class SubtitlePanel(QWidget):
    def __init__(
        self,
        i18n: I18N,
        on_submit: Callable[[SubtitleJobInput, str], None],
        on_download_model: Callable[[str, str | None, str], None],
        on_warmup_model: Callable[[str, str | None, str], None],
        on_unload_model: Callable[[], None],
        on_test_asr_connection: Callable[[SubtitleJobInput], None],
        on_test_connection: Callable[[SubtitleJobInput], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._on_submit = on_submit
        self._on_download_model = on_download_model
        self._on_warmup_model = on_warmup_model
        self._on_unload_model = on_unload_model
        self._on_test_asr_connection = on_test_asr_connection
        self._on_test_connection = on_test_connection
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
        left_root = QVBoxLayout(left)
        left_root.setContentsMargins(0, 0, 0, 0)
        left_root.setSpacing(0)

        scroll = QScrollArea(left)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("OpsScroll")
        scroll.viewport().setAutoFillBackground(False)
        left_root.addWidget(scroll, 1)

        panel = QWidget(self)
        panel.setObjectName("OpsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 6, 8, 8)
        panel_layout.setSpacing(dt.SPACING_8)

        io_box = QFrame(panel)
        io_box.setObjectName("PanelGroup")
        io_layout = QVBoxLayout(io_box)
        io_layout.setContentsMargins(10, 10, 10, 10)
        self.io_title = QLabel("")
        self.io_title.setObjectName("GroupTitle")
        io_layout.addWidget(self.io_title)
        io_form = make_form()
        self.preset_label = QLabel("")
        self.media_label = QLabel("")
        self.voice_image_label = QLabel("")
        self.voice_audio_label = QLabel("")
        self.voice_subtitle_label = QLabel("")
        self.out_label = QLabel("")
        self.voice_container_label = QLabel("")
        self.voice_quality_label = QLabel("")
        self.voice_sub_mode_label = QLabel("")

        self.preset_combo = NoWheelComboBox()
        self.preset_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.preset_combo.addItem("", "one_click_normal")
        self.preset_combo.addItem("", "one_click_voice")
        self.preset_combo.addItem("", "step_by_step")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_mode_changed)

        self.video_edit = QLineEdit()
        self.video_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.video_btn = QPushButton()
        self.video_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.video_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.video_btn.clicked.connect(self._pick_video)
        self.media_row = self._picker_row(self.video_edit, self.video_btn)

        self.voice_image_edit = QLineEdit()
        self.voice_image_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.voice_image_edit.textChanged.connect(self._refresh_voice_lossless_availability)
        self.voice_image_btn = QPushButton()
        self.voice_image_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.voice_image_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.voice_image_btn.clicked.connect(self._pick_voice_image)
        self.voice_image_row = self._picker_row(self.voice_image_edit, self.voice_image_btn)

        self.voice_audio_edit = QLineEdit()
        self.voice_audio_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.voice_audio_btn = QPushButton()
        self.voice_audio_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.voice_audio_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.voice_audio_btn.clicked.connect(self._pick_voice_audio)
        self.voice_audio_row = self._picker_row(self.voice_audio_edit, self.voice_audio_btn)

        self.voice_subtitle_edit = QLineEdit()
        self.voice_subtitle_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.voice_subtitle_btn = QPushButton()
        self.voice_subtitle_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.voice_subtitle_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.voice_subtitle_btn.clicked.connect(self._pick_voice_subtitle)
        self.voice_subtitle_row = self._picker_row(self.voice_subtitle_edit, self.voice_subtitle_btn)

        self.out_edit = QLineEdit()
        self.out_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.out_btn = QPushButton()
        self.out_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.out_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.out_btn.clicked.connect(self._pick_output_dir)
        self.out_row = self._picker_row(self.out_edit, self.out_btn)

        self.voice_container_combo = NoWheelComboBox()
        self.voice_container_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.voice_container_combo.addItems(["mkv", "mp4"])

        self.voice_quality_combo = NoWheelComboBox()
        self.voice_quality_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.voice_quality_combo.addItem("", "cpu_h264")
        self.voice_quality_combo.addItem("", "nvidia_h265")
        self.voice_quality_combo.addItem("", "lossless_copy")

        self.voice_sub_mode_combo = NoWheelComboBox()
        self.voice_sub_mode_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.voice_sub_mode_combo.addItem("", "soft")
        self.voice_sub_mode_combo.addItem("", "hard")
        self.voice_sub_mode_combo.currentIndexChanged.connect(self._refresh_voice_lossless_availability)

        io_form.addRow(self.preset_label, self.preset_combo)
        io_form.addRow(self.media_label, self.media_row)
        io_form.addRow(self.voice_image_label, self.voice_image_row)
        io_form.addRow(self.voice_audio_label, self.voice_audio_row)
        io_form.addRow(self.voice_subtitle_label, self.voice_subtitle_row)
        io_form.addRow(self.out_label, self.out_row)
        io_form.addRow(self.voice_container_label, self.voice_container_combo)
        io_form.addRow(self.voice_quality_label, self.voice_quality_combo)
        io_form.addRow(self.voice_sub_mode_label, self.voice_sub_mode_combo)

        apply_label_width(
            (
                self.preset_label,
                self.media_label,
                self.voice_image_label,
                self.voice_audio_label,
                self.voice_subtitle_label,
                self.out_label,
                self.voice_container_label,
                self.voice_quality_label,
                self.voice_sub_mode_label,
            )
        )
        io_layout.addLayout(io_form)

        asr_box = QFrame(panel)
        asr_box.setObjectName("PanelGroup")
        asr_layout = QVBoxLayout(asr_box)
        asr_layout.setContentsMargins(10, 10, 10, 10)
        self.asr_title = QLabel("")
        self.asr_title.setObjectName("GroupTitle")
        asr_layout.addWidget(self.asr_title)
        asr_form = make_form()

        self.asr_backend_label = QLabel("")
        self.whisper_label = QLabel("")
        self.asr_precision_label = QLabel("")
        self.model_dir_label = QLabel("")
        self.asr_api_base_label = QLabel("")
        self.asr_api_key_label = QLabel("")
        self.asr_model_name_label = QLabel("")
        self.source_lang_label = QLabel("")

        self.asr_backend_combo = NoWheelComboBox()
        self.asr_backend_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.asr_backend_combo.addItem("", "faster_whisper")
        self.asr_backend_combo.addItem("", "asr_gemini")
        self.asr_backend_combo.addItem("", "asr_openai")
        self.asr_backend_combo.addItem("", "asr_qwen")
        self.asr_backend_combo.addItem("", "asr_openai_compatible")
        self.asr_backend_combo.currentIndexChanged.connect(self._on_asr_backend_changed)

        self.whisper_model = NoWheelComboBox()
        self.whisper_model.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.whisper_model.addItems(["small", "medium", "large-v3", "large-v3-turbo"])
        self.whisper_model.setCurrentText("large-v3")

        self.asr_precision = NoWheelComboBox()
        self.asr_precision.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.asr_precision.addItem("", "auto")
        self.asr_precision.addItem("", "float16")
        self.asr_precision.addItem("", "int8")
        self.asr_precision.setCurrentIndex(0)

        self.model_dir_edit = QLineEdit()
        self.model_dir_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.model_dir_btn = QPushButton()
        self.model_dir_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.model_dir_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.model_dir_btn.clicked.connect(self._pick_model_dir)

        model_wrap = QWidget()
        model_layout = QHBoxLayout(model_wrap)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setSpacing(dt.SPACING_8)
        model_layout.addWidget(self.model_dir_edit, 1)
        model_layout.addWidget(self.model_dir_btn)

        self.asr_api_base_edit = QLineEdit("https://api.openai.com/v1")
        self.asr_api_base_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.asr_api_key_edit = QLineEdit()
        self.asr_api_key_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.asr_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.asr_model_name_edit = QLineEdit("gpt-4o-mini-transcribe")
        self.asr_model_name_edit.setMinimumHeight(dt.CONTROL_HEIGHT)

        self.source_lang = NoWheelComboBox()
        self.source_lang.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.source_lang.addItems(["auto", "ja", "en", "zh"])

        self.asr_test_btn = QPushButton()
        self.asr_test_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.asr_test_btn.clicked.connect(self._test_asr_connection)

        self.download_model_btn = QPushButton()
        self.download_model_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.download_model_btn.clicked.connect(self._download_model)
        self.warmup_btn = QPushButton()
        self.warmup_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.warmup_btn.clicked.connect(self._warmup)
        self.unload_btn = QPushButton()
        self.unload_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.unload_btn.clicked.connect(self._unload_model)
        asr_actions = QWidget()
        asr_actions_layout = QHBoxLayout(asr_actions)
        asr_actions_layout.setContentsMargins(0, 0, 0, 0)
        asr_actions_layout.setSpacing(dt.SPACING_8)
        asr_actions_layout.addWidget(self.download_model_btn, 1)
        asr_actions_layout.addWidget(self.warmup_btn, 1)
        asr_actions_layout.addWidget(self.unload_btn, 1)

        asr_form.addRow(self.asr_backend_label, self.asr_backend_combo)
        asr_form.addRow(self.whisper_label, self.whisper_model)
        asr_form.addRow(self.asr_precision_label, self.asr_precision)
        asr_form.addRow(self.model_dir_label, model_wrap)
        asr_form.addRow(self.asr_api_base_label, self.asr_api_base_edit)
        asr_form.addRow(self.asr_api_key_label, self.asr_api_key_edit)
        asr_form.addRow(self.asr_model_name_label, self.asr_model_name_edit)
        asr_form.addRow(self.source_lang_label, self.source_lang)
        asr_form.addRow("", self.asr_test_btn)
        asr_form.addRow("", asr_actions)
        apply_label_width(
            (
                self.asr_backend_label,
                self.whisper_label,
                self.asr_precision_label,
                self.model_dir_label,
                self.asr_api_base_label,
                self.asr_api_key_label,
                self.asr_model_name_label,
                self.source_lang_label,
            )
        )
        asr_layout.addLayout(asr_form)

        tr_box = QFrame(panel)
        tr_box.setObjectName("PanelGroup")
        tr_layout = QVBoxLayout(tr_box)
        tr_layout.setContentsMargins(10, 10, 10, 10)
        self.tr_title = QLabel("")
        self.tr_title.setObjectName("GroupTitle")
        tr_layout.addWidget(self.tr_title)
        tr_form = make_form()
        self.provider_label = QLabel("")
        self.target_lang_label = QLabel("")
        self.api_base_label = QLabel("")
        self.api_key_label = QLabel("")
        self.model_name_label = QLabel("")
        self.extra_headers_label = QLabel("")

        self.provider_combo = NoWheelComboBox()
        self.provider_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.provider_combo.addItems(["none", "openai", "qwen", "deepseek", "openrouter", "gemini_official", "lmstudio", "ollama", "openai_compatible"])
        self.provider_combo.currentTextChanged.connect(self._apply_provider_preset)

        self.target_lang = NoWheelComboBox()
        self.target_lang.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.target_lang.addItems(["zh", "ja", "en"])
        self.target_lang.setCurrentText("zh")

        self.api_base_edit = QLineEdit()
        self.api_base_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.model_name_edit = QLineEdit("gpt-4o-mini")
        self.model_name_edit.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.extra_headers_edit = QLineEdit("{}")
        self.extra_headers_edit.setMinimumHeight(dt.CONTROL_HEIGHT)

        self.test_btn = QPushButton()
        self.test_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.test_btn.clicked.connect(self._test_connection)

        tr_form.addRow(self.provider_label, self.provider_combo)
        tr_form.addRow(self.target_lang_label, self.target_lang)
        tr_form.addRow(self.api_base_label, self.api_base_edit)
        tr_form.addRow(self.api_key_label, self.api_key_edit)
        tr_form.addRow(self.model_name_label, self.model_name_edit)
        tr_form.addRow(self.extra_headers_label, self.extra_headers_edit)
        tr_form.addRow("", self.test_btn)
        apply_label_width((self.provider_label, self.target_lang_label, self.api_base_label, self.api_key_label, self.model_name_label, self.extra_headers_label))
        tr_layout.addLayout(tr_form)

        exec_box = QFrame(panel)
        exec_box.setObjectName("PanelGroup")
        exec_layout = QVBoxLayout(exec_box)
        exec_layout.setContentsMargins(10, 10, 10, 10)
        self.exec_title = QLabel("")
        self.exec_title.setObjectName("GroupTitle")
        exec_layout.addWidget(self.exec_title)

        self.auto_unload_badge = QLabel("?")
        self.auto_unload_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.auto_unload_badge.setFixedSize(18, 18)
        self.auto_unload_badge.setStyleSheet(
            "QLabel {font-weight:700;font-size:12px;color:#059669;border:1px solid #059669;"
            "border-radius:9px;background:rgba(255,255,255,0.92);}"
        )
        self.auto_unload_label = QLabel("")
        self.auto_unload_label.setStyleSheet("font-weight:600;")
        self.auto_unload_check = QCheckBox()
        self.auto_unload_check.setObjectName("AutoUnloadCheck")
        self.auto_unload_check.setChecked(False)
        self.auto_unload_check.setText("")
        auto_unload_row = QWidget()
        auto_unload_layout = QHBoxLayout(auto_unload_row)
        auto_unload_layout.setContentsMargins(0, 0, 0, 0)
        auto_unload_layout.setSpacing(6)
        auto_unload_layout.addWidget(self.auto_unload_badge)
        auto_unload_layout.addWidget(self.auto_unload_label)
        auto_unload_layout.addWidget(self.auto_unload_check)
        auto_unload_layout.addStretch(1)
        exec_layout.addWidget(auto_unload_row)

        self.start_btn = QPushButton()
        self.start_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.start_btn.clicked.connect(lambda: self._submit("all"))
        self.asr_only_btn = QPushButton()
        self.asr_only_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.asr_only_btn.clicked.connect(lambda: self._submit("asr_only"))
        self.translate_only_btn = QPushButton()
        self.translate_only_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.translate_only_btn.clicked.connect(lambda: self._submit("translate_only"))
        self.embed_only_btn = QPushButton()
        self.embed_only_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.embed_only_btn.clicked.connect(lambda: self._submit("embed_only"))

        action1 = QWidget()
        action1_row = QHBoxLayout(action1)
        action1_row.setContentsMargins(0, 0, 0, 0)
        action1_row.setSpacing(dt.SPACING_8)
        action1_row.addWidget(self.start_btn, 1)
        action1_row.addWidget(self.asr_only_btn, 1)

        action2 = QWidget()
        action2_row = QHBoxLayout(action2)
        action2_row.setContentsMargins(0, 0, 0, 0)
        action2_row.setSpacing(dt.SPACING_8)
        action2_row.addWidget(self.translate_only_btn, 1)
        action2_row.addWidget(self.embed_only_btn, 1)

        exec_layout.addWidget(action1)
        exec_layout.addWidget(action2)

        panel_layout.addWidget(io_box)
        panel_layout.addWidget(asr_box)
        panel_layout.addWidget(tr_box)
        panel_layout.addWidget(exec_box)
        panel_layout.addStretch(1)

        scroll.setWidget(panel)

        right = QWidget(self)
        right.setObjectName("LogPane")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 8, 10, 8)
        right_layout.setSpacing(dt.SPACING_8)
        right.setMinimumWidth(410)
        right.setMaximumWidth(460)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("GroupTitle")
        self.clear_log_btn = QPushButton()
        self.clear_log_btn.setMinimumHeight(dt.COMPACT_BUTTON_HEIGHT)
        self.clear_log_btn.clicked.connect(self._clear_log)
        head_row = QWidget()
        head_layout = QHBoxLayout(head_row)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(dt.SPACING_8)
        head_layout.addWidget(self.progress_label, 1)
        head_layout.addWidget(self.clear_log_btn)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(320)
        right_layout.addWidget(head_row)
        right_layout.addWidget(self.progress)
        right_layout.addWidget(self.log_text, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([860, 430])

    def retranslate_ui(self) -> None:
        self.io_title.setText(self.i18n.t("subtitle.group.io"))
        self.asr_title.setText(self.i18n.t("subtitle.group.asr"))
        self.tr_title.setText(self.i18n.t("subtitle.group.translator"))
        self.exec_title.setText(self.i18n.t("subtitle.group.execute"))
        self.preset_label.setText(self.i18n.t("subtitle.preset_mode"))
        self.preset_combo.setItemText(0, self.i18n.t("subtitle.preset_mode.one_click_normal"))
        self.preset_combo.setItemText(1, self.i18n.t("subtitle.preset_mode.one_click_voice"))
        self.preset_combo.setItemText(2, self.i18n.t("subtitle.preset_mode.step_by_step"))
        self.media_label.setText(self.i18n.t("subtitle.input_media"))
        self.voice_image_label.setText(self.i18n.t("subtitle.voice.image"))
        self.voice_audio_label.setText(self.i18n.t("subtitle.voice.audio"))
        self.voice_subtitle_label.setText(self.i18n.t("subtitle.voice.subtitle"))
        self.out_label.setText(self.i18n.t("subtitle.output_dir"))
        self.voice_container_label.setText(self.i18n.t("merge.output_format"))
        self.voice_quality_label.setText(self.i18n.t("merge.priority"))
        self.voice_sub_mode_label.setText(self.i18n.t("merge.subtitle_mode"))
        self.voice_quality_combo.setItemText(0, self.i18n.t("merge.priority.cpu_h264"))
        self.voice_quality_combo.setItemText(1, self.i18n.t("merge.priority.nvidia_h265"))
        self.voice_quality_combo.setItemText(2, self.i18n.t("merge.priority.lossless_copy"))
        self.voice_sub_mode_combo.setItemText(0, self.i18n.t("merge.subtitle_mode.soft"))
        self.voice_sub_mode_combo.setItemText(1, self.i18n.t("merge.subtitle_mode.hard"))
        self.asr_backend_label.setText(self.i18n.t("subtitle.asr_backend"))
        self.asr_backend_combo.setItemText(0, self.i18n.t("subtitle.asr_backend.local"))
        self.asr_backend_combo.setItemText(1, self.i18n.t("subtitle.asr_backend.gemini"))
        self.asr_backend_combo.setItemText(2, self.i18n.t("subtitle.asr_backend.openai"))
        self.asr_backend_combo.setItemText(3, self.i18n.t("subtitle.asr_backend.qwen"))
        self.asr_backend_combo.setItemText(4, self.i18n.t("subtitle.asr_backend.compatible"))
        self.whisper_label.setText(self.i18n.t("subtitle.whisper_model"))
        self.asr_precision_label.setText(self.i18n.t("subtitle.asr_precision"))
        self.model_dir_label.setText(self.i18n.t("subtitle.model_dir"))
        self.asr_api_base_label.setText(self.i18n.t("subtitle.asr_api_base"))
        self.asr_api_key_label.setText(self.i18n.t("subtitle.asr_api_key"))
        self.asr_model_name_label.setText(self.i18n.t("subtitle.asr_model_name"))
        self.source_lang_label.setText(self.i18n.t("subtitle.source_lang"))
        self.provider_label.setText(self.i18n.t("subtitle.translate_provider"))
        self.target_lang_label.setText(self.i18n.t("subtitle.target_lang"))
        self.api_base_label.setText(self.i18n.t("subtitle.api_base"))
        self.api_key_label.setText(self.i18n.t("subtitle.api_key"))
        self.model_name_label.setText(self.i18n.t("subtitle.model_name"))
        self.extra_headers_label.setText(self.i18n.t("subtitle.extra_headers"))
        self.progress_label.setText(self.i18n.t("merge.progress"))
        self.video_btn.setText(self.i18n.t("common.select"))
        self.voice_image_btn.setText(self.i18n.t("common.select"))
        self.voice_audio_btn.setText(self.i18n.t("common.select"))
        self.voice_subtitle_btn.setText(self.i18n.t("common.select"))
        self.out_btn.setText(self.i18n.t("common.select"))
        self.model_dir_btn.setText(self.i18n.t("common.select"))
        self.download_model_btn.setText(self.i18n.t("subtitle.download_model"))
        self.warmup_btn.setText(self.i18n.t("subtitle.preheat_model"))
        self.unload_btn.setText(self.i18n.t("subtitle.unload_model"))
        self.asr_test_btn.setText(self.i18n.t("subtitle.test_asr_connection"))
        self.test_btn.setText(self.i18n.t("subtitle.test_connection"))
        self.start_btn.setText(self.i18n.t("subtitle.start"))
        self.asr_only_btn.setText(self.i18n.t("subtitle.asr_only"))
        self.translate_only_btn.setText(self.i18n.t("subtitle.translate_only"))
        self.embed_only_btn.setText(self.i18n.t("subtitle.embed_only"))
        self.auto_unload_label.setText(self.i18n.t("subtitle.auto_unload_label"))
        self.auto_unload_badge.setToolTip(self.i18n.t("subtitle.auto_unload_hint"))
        self.clear_log_btn.setText(self.i18n.t("common.clear"))
        self._set_asr_precision_labels()
        self._refresh_voice_lossless_availability()
        self._on_preset_mode_changed()
        self._on_asr_backend_changed()

    def _set_asr_precision_labels(self) -> None:
        options = [
            ("auto", self.i18n.t("subtitle.asr_precision_auto")),
            ("float16", self.i18n.t("subtitle.asr_precision_float16")),
            ("int8", self.i18n.t("subtitle.asr_precision_int8")),
        ]
        current = str(self.asr_precision.currentData() or "auto")
        self.asr_precision.blockSignals(True)
        self.asr_precision.clear()
        for value, label in options:
            self.asr_precision.addItem(label, value)
        idx = self.asr_precision.findData(current)
        self.asr_precision.setCurrentIndex(idx if idx >= 0 else 0)
        self.asr_precision.blockSignals(False)

    def _pick_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.i18n.t("subtitle.input_media"),
            "",
            "Media (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.wmv *.m4v *.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus)",
        )
        if path:
            self.video_edit.setText(path)

    def _pick_voice_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.i18n.t("subtitle.voice.image"),
            "",
            "Image (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self.voice_image_edit.setText(path)
            self._refresh_voice_lossless_availability()

    def _pick_voice_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.i18n.t("subtitle.voice.audio"),
            "",
            "Audio (*.mp3 *.wav *.flac *.m4a *.aac *.ogg *.opus)",
        )
        if path:
            self.voice_audio_edit.setText(path)

    def _pick_voice_subtitle(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.i18n.t("subtitle.voice.subtitle"),
            "",
            "Subtitle (*.srt *.ass *.ssa *.vtt *.sub)",
        )
        if path:
            self.voice_subtitle_edit.setText(path)

    def _pick_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.i18n.t("subtitle.output_dir"))
        if path:
            self.out_edit.setText(path)

    def _pick_model_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.i18n.t("subtitle.model_dir"))
        if path:
            self.model_dir_edit.setText(path)

    def _download_model(self) -> None:
        self._on_download_model(
            self.whisper_model.currentText(),
            self.model_dir_edit.text().strip() or None,
            str(self.asr_precision.currentData() or "auto"),
        )

    def _warmup(self) -> None:
        self._on_warmup_model(
            self.whisper_model.currentText(),
            self.model_dir_edit.text().strip() or None,
            str(self.asr_precision.currentData() or "auto"),
        )

    def _unload_model(self) -> None:
        self._on_unload_model()

    def _test_connection(self) -> None:
        payload = self._build_payload()
        if payload:
            self._on_test_connection(payload)

    def _test_asr_connection(self) -> None:
        payload = self._build_payload()
        if payload:
            self._on_test_asr_connection(payload)

    def _build_payload(self) -> SubtitleJobInput | None:
        headers_raw = self.extra_headers_edit.text().strip() or "{}"
        try:
            headers = json.loads(headers_raw)
            if not isinstance(headers, dict):
                raise ValueError("headers must be object")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "JSON", f"Invalid extra headers JSON: {exc}")
            return None

        return SubtitleJobInput(
            video_path=self.video_edit.text().strip(),
            output_dir=self.out_edit.text().strip(),
            preset_mode=str(self.preset_combo.currentData() or "step_by_step"),  # type: ignore[arg-type]
            voice_image_path=self.voice_image_edit.text().strip() or None,
            voice_audio_path=self.voice_audio_edit.text().strip() or None,
            voice_subtitle_path=self.voice_subtitle_edit.text().strip() or None,
            voice_output_container=str(self.voice_container_combo.currentText() or "mkv"),  # type: ignore[arg-type]
            voice_output_quality=str(self.voice_quality_combo.currentData() or "cpu_h264"),  # type: ignore[arg-type]
            voice_subtitle_mode=str(self.voice_sub_mode_combo.currentData() or "soft"),  # type: ignore[arg-type]
            asr_backend=str(self.asr_backend_combo.currentData() or "faster_whisper"),  # type: ignore[arg-type]
            whisper_model=self.whisper_model.currentText(),  # type: ignore[arg-type]
            asr_compute_type=str(self.asr_precision.currentData() or "auto"),  # type: ignore[arg-type]
            model_dir=self.model_dir_edit.text().strip() or None,
            asr_api_base_url=self.asr_api_base_edit.text().strip() or None,
            asr_api_key=self.asr_api_key_edit.text().strip() or None,
            asr_model_name=self.asr_model_name_edit.text().strip() or "gpt-4o-mini-transcribe",
            source_lang=self.source_lang.currentText(),
            target_lang=self.target_lang.currentText(),
            translator_provider=self.provider_combo.currentText(),  # type: ignore[arg-type]
            api_base_url=self.api_base_edit.text().strip() or None,
            api_key=self.api_key_edit.text().strip() or None,
            model_name=self.model_name_edit.text().strip() or "gpt-4o-mini",
            extra_headers={str(k): str(v) for k, v in headers.items()} if headers else None,
            auto_unload_after_asr=self.auto_unload_check.isChecked(),
        )

    def _apply_provider_preset(self, provider: str) -> None:
        presets = {
            "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
            "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
            "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
            "openrouter": ("https://openrouter.ai/api/v1", "google/gemini-2.0-flash-001"),
            "gemini_official": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
            "lmstudio": ("http://127.0.0.1:1234/v1", "local-model"),
            "ollama": ("http://127.0.0.1:11434/v1", "qwen2.5:7b"),
            "openai_compatible": ("", "gpt-4o-mini"),
            "none": ("", ""),
        }
        base, model = presets.get(provider, ("", ""))
        self.api_base_edit.setText(base)
        self.model_name_edit.setText(model)

    def _apply_asr_backend_preset(self, backend: str) -> None:
        presets = {
            "asr_gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash"),
            "asr_openai": ("https://api.openai.com/v1", "gpt-4o-mini-transcribe"),
            "asr_qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-asr-flash"),
            "asr_openai_compatible": ("", "gpt-4o-mini-transcribe"),
        }
        if backend in presets:
            base, model = presets[backend]
            self.asr_api_base_edit.setText(base)
            self.asr_model_name_edit.setText(model)

    def _on_preset_mode_changed(self, *_args) -> None:
        mode = str(self.preset_combo.currentData() or "step_by_step")
        is_voice = mode == "one_click_voice"
        is_step = mode == "step_by_step"
        self._set_row_visible(self.media_label, self.media_row, not is_voice)
        self._set_row_visible(self.voice_image_label, self.voice_image_row, is_voice)
        self._set_row_visible(self.voice_audio_label, self.voice_audio_row, is_voice)
        self._set_row_visible(self.voice_subtitle_label, self.voice_subtitle_row, is_voice)
        self._set_row_visible(self.voice_container_label, self.voice_container_combo, is_voice)
        self._set_row_visible(self.voice_quality_label, self.voice_quality_combo, is_voice)
        self._set_row_visible(self.voice_sub_mode_label, self.voice_sub_mode_combo, is_voice)
        self.asr_only_btn.setEnabled(is_step)
        self.translate_only_btn.setEnabled(is_step)
        self.embed_only_btn.setEnabled(is_step)
        self.start_btn.setEnabled(not is_step)
        self._refresh_voice_lossless_availability()

    def _refresh_voice_lossless_availability(self, *_args) -> None:
        idx = self.voice_quality_combo.findData("lossless_copy")
        if idx < 0:
            return
        mode = str(self.preset_combo.currentData() or "step_by_step")
        block = mode == "one_click_voice" and bool(self.voice_image_edit.text().strip())
        model = self.voice_quality_combo.model()
        item = getattr(model, "item", lambda *_: None)(idx)
        if item is not None:
            item.setEnabled(not block)
        if block and self.voice_quality_combo.currentIndex() == idx:
            self.voice_quality_combo.setCurrentIndex(0)
        if block:
            self.voice_quality_combo.setToolTip(self.i18n.t("merge.lossless_blocked"))
        else:
            self.voice_quality_combo.setToolTip("")

    def _submit(self, mode: str = "all") -> None:
        payload = self._build_payload()
        if not payload:
            return
        if not payload.output_dir:
            self.append_log("Please select output directory.")
            return
        if payload.preset_mode in {"one_click_normal", "step_by_step"}:
            if not payload.video_path:
                self.append_log("Please select input media and output directory.")
                return
        if payload.preset_mode == "one_click_voice":
            if not payload.voice_image_path or not payload.voice_audio_path:
                self.append_log("Audio-localization mode requires image and audio.")
                return
            mode = "all"
        elif payload.preset_mode == "one_click_normal":
            mode = "all"
        elif payload.preset_mode == "step_by_step":
            if mode == "embed_only":
                lower = payload.video_path.lower()
                if lower.endswith((".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma")):
                    self.append_log(self.i18n.t("subtitle.embed_invalid_audio"))
                    return
        self._on_submit(payload, mode)

    def append_log(self, line: str) -> None:
        self.log_text.append(line)

    def set_progress(self, percent: float, status: str = "") -> None:
        self.progress.setValue(int(max(0, min(100, percent))))

    def _clear_log(self) -> None:
        self.log_text.clear()

    def apply_defaults(
        self,
        model_dir: str,
        profile: dict[str, str] | None = None,
        compute_preference: str = "auto",
        auto_unload_after_asr: bool = False,
    ) -> None:
        if model_dir:
            self.model_dir_edit.setText(model_dir)
        pref_idx = self.asr_precision.findData(compute_preference)
        if pref_idx >= 0:
            self.asr_precision.setCurrentIndex(pref_idx)
        self.auto_unload_check.setChecked(bool(auto_unload_after_asr))
        if profile:
            self.provider_combo.setCurrentText(profile.get("provider", "none"))
            self.api_base_edit.setText(profile.get("base_url", ""))
            self.model_name_edit.setText(profile.get("model", "gpt-4o-mini"))
        idx = self.preset_combo.findData("step_by_step")
        self.preset_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._on_preset_mode_changed()
        self._on_asr_backend_changed()

    def export_state(self) -> dict[str, object]:
        return {
            "preset_mode": str(self.preset_combo.currentData() or "step_by_step"),
            "media_path": self.video_edit.text().strip(),
            "output_dir": self.out_edit.text().strip(),
            "voice_image_path": self.voice_image_edit.text().strip(),
            "voice_audio_path": self.voice_audio_edit.text().strip(),
            "voice_subtitle_path": self.voice_subtitle_edit.text().strip(),
            "voice_output_container": self.voice_container_combo.currentText(),
            "voice_output_quality": str(self.voice_quality_combo.currentData() or "cpu_h264"),
            "voice_subtitle_mode": str(self.voice_sub_mode_combo.currentData() or "soft"),
            "asr_backend": str(self.asr_backend_combo.currentData() or "faster_whisper"),
            "whisper_model": self.whisper_model.currentText(),
            "asr_precision": str(self.asr_precision.currentData() or "auto"),
            "model_dir": self.model_dir_edit.text().strip(),
            "asr_api_base": self.asr_api_base_edit.text().strip(),
            "asr_api_key": self.asr_api_key_edit.text().strip(),
            "asr_model_name": self.asr_model_name_edit.text().strip(),
            "source_lang": self.source_lang.currentText(),
            "provider": self.provider_combo.currentText(),
            "target_lang": self.target_lang.currentText(),
            "api_base": self.api_base_edit.text().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "model_name": self.model_name_edit.text().strip(),
            "extra_headers": self.extra_headers_edit.text().strip(),
            "auto_unload_after_asr": self.auto_unload_check.isChecked(),
        }

    def apply_saved_state(self, state: dict[str, object] | None) -> None:
        if not state:
            return

        preset = str(state.get("preset_mode", "") or "")
        p_idx = self.preset_combo.findData(preset)
        if p_idx >= 0:
            self.preset_combo.setCurrentIndex(p_idx)

        media_path = str(state.get("media_path", "") or "").strip()
        if media_path:
            self.video_edit.setText(media_path)
        out_dir = str(state.get("output_dir", "") or "").strip()
        if out_dir:
            self.out_edit.setText(out_dir)
        voice_img = str(state.get("voice_image_path", "") or "").strip()
        if voice_img:
            self.voice_image_edit.setText(voice_img)
        voice_audio = str(state.get("voice_audio_path", "") or "").strip()
        if voice_audio:
            self.voice_audio_edit.setText(voice_audio)
        voice_sub = str(state.get("voice_subtitle_path", "") or "").strip()
        if voice_sub:
            self.voice_subtitle_edit.setText(voice_sub)

        c_idx = self.voice_container_combo.findText(str(state.get("voice_output_container", "") or ""))
        if c_idx >= 0:
            self.voice_container_combo.setCurrentIndex(c_idx)
        q_idx = self.voice_quality_combo.findData(str(state.get("voice_output_quality", "") or ""))
        if q_idx >= 0:
            self.voice_quality_combo.setCurrentIndex(q_idx)
        sm_idx = self.voice_sub_mode_combo.findData(str(state.get("voice_subtitle_mode", "") or ""))
        if sm_idx >= 0:
            self.voice_sub_mode_combo.setCurrentIndex(sm_idx)

        asr_backend = str(state.get("asr_backend", "") or "")
        ab_idx = self.asr_backend_combo.findData(asr_backend)
        if ab_idx >= 0:
            self.asr_backend_combo.setCurrentIndex(ab_idx)
        wm = str(state.get("whisper_model", "") or "")
        if wm:
            self.whisper_model.setCurrentText(wm)
        ap_idx = self.asr_precision.findData(str(state.get("asr_precision", "") or ""))
        if ap_idx >= 0:
            self.asr_precision.setCurrentIndex(ap_idx)
        model_dir = str(state.get("model_dir", "") or "").strip()
        if model_dir:
            self.model_dir_edit.setText(model_dir)
        self.asr_api_base_edit.setText(str(state.get("asr_api_base", "") or "").strip())
        self.asr_api_key_edit.setText(str(state.get("asr_api_key", "") or "").strip())
        self.asr_model_name_edit.setText(str(state.get("asr_model_name", "") or "").strip())
        src_idx = self.source_lang.findText(str(state.get("source_lang", "") or ""))
        if src_idx >= 0:
            self.source_lang.setCurrentIndex(src_idx)

        provider = str(state.get("provider", "") or "")
        pv_idx = self.provider_combo.findText(provider)
        if pv_idx >= 0:
            self.provider_combo.setCurrentIndex(pv_idx)
        tgt_idx = self.target_lang.findText(str(state.get("target_lang", "") or ""))
        if tgt_idx >= 0:
            self.target_lang.setCurrentIndex(tgt_idx)
        self.api_base_edit.setText(str(state.get("api_base", "") or "").strip())
        self.api_key_edit.setText(str(state.get("api_key", "") or "").strip())
        self.model_name_edit.setText(str(state.get("model_name", "") or "").strip())
        headers = str(state.get("extra_headers", "") or "").strip()
        if headers:
            self.extra_headers_edit.setText(headers)
        self.auto_unload_check.setChecked(bool(state.get("auto_unload_after_asr", False)))

        self._on_preset_mode_changed()
        self._refresh_voice_lossless_availability()

    def set_model_action_running(self, running: bool) -> None:
        self.download_model_btn.setEnabled(not running and self._is_local_asr())
        self.warmup_btn.setEnabled(not running and self._is_local_asr())
        self.unload_btn.setEnabled(not running and self._is_local_asr())
        self.asr_test_btn.setEnabled((not running) and (not self._is_local_asr()))

    def _is_local_asr(self) -> bool:
        return str(self.asr_backend_combo.currentData() or "faster_whisper") == "faster_whisper"

    def _on_asr_backend_changed(self) -> None:
        backend = str(self.asr_backend_combo.currentData() or "faster_whisper")
        self._apply_asr_backend_preset(backend)
        local = self._is_local_asr()
        self.whisper_model.setEnabled(local)
        self.asr_precision.setEnabled(local)
        self.model_dir_edit.setEnabled(local)
        self.model_dir_btn.setEnabled(local)
        self.download_model_btn.setEnabled(local)
        self.warmup_btn.setEnabled(local)
        self.unload_btn.setEnabled(local)
        self.asr_test_btn.setEnabled(not local)
        self.asr_api_base_edit.setEnabled(not local)
        self.asr_api_key_edit.setEnabled(not local)
        self.asr_model_name_edit.setEnabled(not local)
        self.auto_unload_check.setEnabled(local)

    @staticmethod
    def _picker_row(edit: QLineEdit, btn: QPushButton) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(dt.SPACING_8)
        row.addWidget(edit, 1)
        row.addWidget(btn)
        return wrap

    @staticmethod
    def _set_row_visible(label: QLabel, field: QWidget, visible: bool) -> None:
        label.setVisible(visible)
        field.setVisible(visible)

    @staticmethod
    def _with_help(text: str, tooltip: str) -> QWidget:
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
        badge.setStyleSheet(
            "QLabel {font-weight:700;font-size:12px;color:#059669;border:1px solid #059669;"
            "border-radius:9px;background:rgba(255,255,255,0.92);}"
        )
        row.addWidget(title)
        row.addWidget(badge)
        row.addStretch(1)
        return wrap
