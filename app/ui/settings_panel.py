from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen, QResizeEvent, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QSlider,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)

from app.core.i18n import I18N
from app.ui import design_tokens as dt
from app.ui.layout.form_grid import apply_label_width, make_form


class PreviewImageFrame(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pix = QPixmap()
        self._empty_text = "No Image"
        self.setMinimumHeight(220)
        self.setFrameShape(QFrame.Shape.Box)

    def set_image(self, pix: QPixmap) -> None:
        self._pix = pix
        self.update()

    def clear_image(self) -> None:
        self._pix = QPixmap()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)

        if self._pix.isNull():
            p.setPen(QPen(QColor(230, 236, 246, 220)))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._empty_text)
            return

        # Layer 1: full-bleed background fill (softened by low opacity + dark veil).
        bg = self._pix.scaled(rect.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        bx = rect.x() + (rect.width() - bg.width()) // 2
        by = rect.y() + (rect.height() - bg.height()) // 2
        p.setOpacity(0.28)
        p.drawPixmap(bx, by, bg)
        p.setOpacity(1.0)
        p.fillRect(rect, QColor(8, 12, 18, 95))

        # Layer 2: foreground image keeps full composition without cropping.
        fg_rect = rect.adjusted(10, 10, -10, -10)
        fg = self._pix.scaled(fg_rect.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        fx = fg_rect.x() + (fg_rect.width() - fg.width()) // 2
        fy = fg_rect.y() + (fg_rect.height() - fg.height()) // 2
        p.drawPixmap(fx, fy, fg)


class SettingsPanel(QWidget):
    def __init__(
        self,
        i18n: I18N,
        on_pick_background: Callable[[], None],
        on_reset_background: Callable[[], None],
        on_pick_preview: Callable[[int], None],
        on_reset_preview: Callable[[int], None],
        on_save_paths: Callable[[str, str], None],
        on_language_change: Callable[[str], None],
        on_env_check: Callable[[], None],
        app_version: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self._on_pick_background = on_pick_background
        self._on_reset_background = on_reset_background
        self._on_pick_preview = on_pick_preview
        self._on_reset_preview = on_reset_preview
        self._on_save_paths = on_save_paths
        self._on_language_change = on_language_change
        self._on_env_check = on_env_check
        self._app_version = app_version
        self._preview_sources: dict[int, QPixmap] = {1: QPixmap(), 2: QPixmap()}
        self._build_ui()
        self.i18n.subscribe(self.retranslate_ui)
        self.retranslate_ui()

    @staticmethod
    def _make_link_label(text: str, url: str) -> QLabel:
        label = QLabel(f"<a href='{url}'><span style='color:#dbeafe; text-decoration: underline;'>{text}</span></a>")
        label.setOpenExternalLinks(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        return label

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

        runtime_box = QFrame(left)
        runtime_box.setObjectName("PanelGroup")
        runtime_layout = QVBoxLayout(runtime_box)
        runtime_layout.setContentsMargins(10, 10, 10, 10)
        self.runtime_title = QLabel("")
        self.runtime_title.setObjectName("GroupTitle")
        runtime_layout.addWidget(self.runtime_title)
        runtime_form = make_form()

        self.ffmpeg_path = QLineEdit()
        self.ffmpeg_path.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.ffmpeg_path.setReadOnly(True)
        self.ffmpeg_path.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ffmpeg_btn = QPushButton()
        self.ffmpeg_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.ffmpeg_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.ffmpeg_btn.clicked.connect(lambda: self._pick_file(self.ffmpeg_path, "ffmpeg.exe"))

        self.ffprobe_path = QLineEdit()
        self.ffprobe_path.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.ffprobe_path.setReadOnly(True)
        self.ffprobe_path.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ffprobe_btn = QPushButton()
        self.ffprobe_btn.setFixedWidth(dt.PICK_BUTTON_WIDTH)
        self.ffprobe_btn.setFixedHeight(dt.CONTROL_HEIGHT)
        self.ffprobe_btn.clicked.connect(lambda: self._pick_file(self.ffprobe_path, "ffprobe.exe"))

        self.save_paths_btn = QPushButton()
        self.save_paths_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.save_paths_btn.clicked.connect(lambda: self._on_save_paths(self.ffmpeg_path.text().strip(), self.ffprobe_path.text().strip()))

        ffmpeg_row = self._path_row(self.ffmpeg_path, self.ffmpeg_btn)
        ffprobe_row = self._path_row(self.ffprobe_path, self.ffprobe_btn)

        self.ffmpeg_label = QLabel("")
        self.ffprobe_label = QLabel("")
        runtime_form.addRow(self.ffmpeg_label, ffmpeg_row)
        runtime_form.addRow(self.ffprobe_label, ffprobe_row)
        runtime_form.addRow("", self.save_paths_btn)
        apply_label_width((self.ffmpeg_label, self.ffprobe_label))
        runtime_layout.addLayout(runtime_form)

        appearance_box = QFrame(left)
        appearance_box.setObjectName("PanelGroup")
        appearance_layout = QVBoxLayout(appearance_box)
        appearance_layout.setContentsMargins(10, 10, 10, 10)
        self.appearance_title = QLabel("")
        self.appearance_title.setObjectName("GroupTitle")
        appearance_layout.addWidget(self.appearance_title)
        appearance_form = make_form()

        self.pick_bg_btn = QPushButton()
        self.pick_bg_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.pick_bg_btn.clicked.connect(self._on_pick_background)
        self.reset_bg_btn = QPushButton()
        self.reset_bg_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.reset_bg_btn.clicked.connect(self._on_reset_background)

        bg_row = QWidget()
        bg_layout = QHBoxLayout(bg_row)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        bg_layout.setSpacing(dt.SPACING_8)
        bg_layout.addWidget(self.pick_bg_btn)
        bg_layout.addWidget(self.reset_bg_btn)

        self.blur_slider = QSlider(Qt.Orientation.Horizontal)
        self.blur_slider.setMinimum(0)
        self.blur_slider.setMaximum(30)
        self.blur_slider.setValue(12)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setMinimum(50)
        self.opacity_slider.setMaximum(90)
        self.opacity_slider.setValue(78)

        self.bg_label = QLabel("")
        self.blur_label = QLabel("")
        self.opacity_label = QLabel("")
        appearance_form.addRow(self.bg_label, bg_row)
        appearance_form.addRow(self.blur_label, self.blur_slider)
        appearance_form.addRow(self.opacity_label, self.opacity_slider)
        apply_label_width((self.bg_label, self.blur_label, self.opacity_label))
        appearance_layout.addLayout(appearance_form)

        general_box = QFrame(left)
        general_box.setObjectName("PanelGroup")
        general_layout = QVBoxLayout(general_box)
        general_layout.setContentsMargins(10, 10, 10, 10)
        self.general_title = QLabel("")
        self.general_title.setObjectName("GroupTitle")
        general_layout.addWidget(self.general_title)
        general_form = make_form()

        self.language_combo = QComboBox()
        self.language_combo.setMinimumHeight(dt.CONTROL_HEIGHT)
        self.language_combo.addItem("中文", "zh")
        self.language_combo.addItem("日本語", "ja")
        self.language_combo.addItem("English", "en")
        self.language_combo.currentIndexChanged.connect(self._on_language_index_changed)

        self.language_label = QLabel("")
        general_form.addRow(self.language_label, self.language_combo)
        apply_label_width((self.language_label,))
        general_layout.addLayout(general_form)

        left_layout.addWidget(runtime_box)
        left_layout.addWidget(appearance_box)
        left_layout.addWidget(general_box)
        env_box = QFrame(left)
        env_box.setObjectName("PanelGroup")
        env_layout = QVBoxLayout(env_box)
        env_layout.setContentsMargins(10, 10, 10, 10)
        env_layout.setSpacing(dt.SPACING_8)

        self.env_title = QLabel("")
        self.env_title.setObjectName("GroupTitle")
        env_layout.addWidget(self.env_title)

        self.env_check_btn = QPushButton("")
        self.env_check_btn.setMinimumHeight(dt.BUTTON_HEIGHT)
        self.env_check_btn.clicked.connect(self._on_env_check)
        env_layout.addWidget(self.env_check_btn)

        env_layout.addSpacing(dt.SPACING_8)
        self.links_title = QLabel("")
        self.links_title.setObjectName("GroupTitle")
        env_layout.addWidget(self.links_title)

        links_row = QWidget()
        links_layout = QHBoxLayout(links_row)
        links_layout.setContentsMargins(0, 0, 0, 0)
        links_layout.setSpacing(dt.SPACING_12)
        self.ffmpeg_link = self._make_link_label("ffmpeg", "https://ffmpeg.org")
        self.ytdlp_link = self._make_link_label("yt-dlp", "https://github.com/yt-dlp/yt-dlp")
        self.whisper_link = self._make_link_label("faster-whisper", "https://github.com/SYSTRAN/faster-whisper")
        self.cuda_link = self._make_link_label("CUDA", "https://developer.nvidia.com/cuda-zone")
        links_layout.addWidget(self.ffmpeg_link)
        links_layout.addWidget(self.ytdlp_link)
        links_layout.addWidget(self.whisper_link)
        links_layout.addWidget(self.cuda_link)
        links_layout.addStretch(1)
        env_layout.addWidget(links_row)

        self.version_label = QLabel("")
        self.version_label.setWordWrap(True)
        env_layout.addWidget(self.version_label)

        left_layout.addWidget(env_box)
        left_layout.addStretch(1)

        right = QWidget(self)
        right.setObjectName("PreviewPane")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(10, 8, 10, 8)
        right_layout.setSpacing(dt.SPACING_8)
        right.setMinimumWidth(430)

        self.preview_title = QLabel("Image Preview")
        self.preview_title.setObjectName("GroupTitle")
        right_layout.addWidget(self.preview_title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(dt.SPACING_8)
        grid.setVerticalSpacing(dt.SPACING_8)

        self.preview_box_1 = QGroupBox()
        self.preview_box_2 = QGroupBox()
        self.preview_box_1.setObjectName("PanelGroup")
        self.preview_box_2.setObjectName("PanelGroup")

        self.preview_label_1 = PreviewImageFrame()
        self.preview_label_2 = PreviewImageFrame()

        self.pick_preview_btn_1 = QPushButton("选择图片 1")
        self.pick_preview_btn_2 = QPushButton("选择图片 2")
        self.reset_preview_btn_1 = QPushButton("恢复默认")
        self.reset_preview_btn_2 = QPushButton("恢复默认")
        self.pick_preview_btn_1.clicked.connect(lambda: self._on_pick_preview(1))
        self.pick_preview_btn_2.clicked.connect(lambda: self._on_pick_preview(2))
        self.reset_preview_btn_1.clicked.connect(lambda: self._on_reset_preview(1))
        self.reset_preview_btn_2.clicked.connect(lambda: self._on_reset_preview(2))

        box1_layout = QVBoxLayout(self.preview_box_1)
        box1_layout.addWidget(self.preview_label_1, 1)
        box1_actions = QWidget()
        box1_actions_layout = QHBoxLayout(box1_actions)
        box1_actions_layout.setContentsMargins(0, 0, 0, 0)
        box1_actions_layout.setSpacing(dt.SPACING_8)
        box1_actions_layout.addWidget(self.pick_preview_btn_1, 1)
        box1_actions_layout.addWidget(self.reset_preview_btn_1, 1)
        box1_layout.addWidget(box1_actions)

        box2_layout = QVBoxLayout(self.preview_box_2)
        box2_layout.addWidget(self.preview_label_2, 1)
        box2_actions = QWidget()
        box2_actions_layout = QHBoxLayout(box2_actions)
        box2_actions_layout.setContentsMargins(0, 0, 0, 0)
        box2_actions_layout.setSpacing(dt.SPACING_8)
        box2_actions_layout.addWidget(self.pick_preview_btn_2, 1)
        box2_actions_layout.addWidget(self.reset_preview_btn_2, 1)
        box2_layout.addWidget(box2_actions)

        grid.addWidget(self.preview_box_1, 0, 0)
        grid.addWidget(self.preview_box_2, 1, 0)
        right_layout.addLayout(grid, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

    @staticmethod
    def _path_row(edit: QLineEdit, button: QPushButton) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(dt.SPACING_8)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(button)
        return row

    def retranslate_ui(self) -> None:
        self.runtime_title.setText(self.i18n.t("settings.group.runtime"))
        self.appearance_title.setText(self.i18n.t("settings.group.appearance"))
        self.general_title.setText(self.i18n.t("settings.group.general"))
        self.env_title.setText(self.i18n.t("settings.group.env_version"))
        self.ffmpeg_label.setText(self.i18n.t("settings.ffmpeg"))
        self.ffprobe_label.setText(self.i18n.t("settings.ffprobe"))
        self.bg_label.setText(self.i18n.t("settings.background"))
        self.blur_label.setText(self.i18n.t("settings.blur"))
        self.opacity_label.setText(self.i18n.t("settings.opacity"))
        self.language_label.setText(self.i18n.t("settings.language"))
        self.ffmpeg_btn.setText(self.i18n.t("common.select"))
        self.ffprobe_btn.setText(self.i18n.t("common.select"))
        self.save_paths_btn.setText(self.i18n.t("settings.save_ffmpeg"))
        self.pick_bg_btn.setText(self.i18n.t("settings.upload_bg"))
        self.reset_bg_btn.setText(self.i18n.t("settings.reset_bg"))
        self.env_check_btn.setText(self.i18n.t("settings.env_check"))
        self.links_title.setText(self.i18n.t("settings.links_title"))
        self.version_label.setText(
            f"{self.i18n.t('settings.version')} {self._app_version} ({self.i18n.t('settings.no_auto_update')})"
        )
        self.pick_preview_btn_1.setText(f"{self.i18n.t('common.select')} 1")
        self.pick_preview_btn_2.setText(f"{self.i18n.t('common.select')} 2")
        self.reset_preview_btn_1.setText(self.i18n.t("settings.reset_bg"))
        self.reset_preview_btn_2.setText(self.i18n.t("settings.reset_bg"))

    def set_preview_image(self, slot: int, path: str) -> None:
        target = self.preview_label_1 if slot == 1 else self.preview_label_2
        pix = QPixmap(path)
        if pix.isNull():
            self._reset_preview(target)
            return
        self._preview_sources[slot] = pix
        self._render_preview(slot)

    def _reset_preview(self, target: PreviewImageFrame) -> None:
        target.clear_image()

    def clear_preview_image(self, slot: int) -> None:
        self._preview_sources[slot] = QPixmap()
        target = self.preview_label_1 if slot == 1 else self.preview_label_2
        self._reset_preview(target)

    def _render_preview(self, slot: int) -> None:
        src = self._preview_sources.get(slot)
        if src is None or src.isNull():
            return
        target = self.preview_label_1 if slot == 1 else self.preview_label_2
        target.set_image(src)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._render_preview(1)
        self._render_preview(2)

    def _pick_file(self, target: QLineEdit, filename_hint: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"{self.i18n.t('common.select')} {filename_hint}", "", "Executable (*.exe)")
        if path:
            target.setText(path)
            target.setCursorPosition(0)
            target.deselect()

    def _on_language_index_changed(self) -> None:
        self._on_language_change(str(self.language_combo.currentData()))

    def set_ffmpeg_paths(self, ffmpeg: str, ffprobe: str) -> None:
        self.ffmpeg_path.setText(ffmpeg)
        self.ffprobe_path.setText(ffprobe)
        self.ffmpeg_path.setCursorPosition(0)
        self.ffprobe_path.setCursorPosition(0)
        self.ffmpeg_path.deselect()
        self.ffprobe_path.deselect()

    def set_language(self, language: str) -> None:
        idx = self.language_combo.findData(language)
        if idx >= 0:
            self.language_combo.setCurrentIndex(idx)
