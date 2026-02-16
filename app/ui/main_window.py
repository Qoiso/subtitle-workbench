from __future__ import annotations

import asyncio
import importlib.metadata
import importlib.util
import re
import subprocess
from pathlib import Path
from time import perf_counter

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFileDialog,
    QGraphicsBlurEffect,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QLabel,
    QComboBox,
    QAbstractSpinBox,
)

from app.core.ffmpeg_service import FFmpegService
from app.core.i18n import I18N
from app.core.models import DownloadInput, MergeInput, SubtitleJobInput, TaskStatus, TaskType
from app.core.subtitle_pipeline_service import SubtitlePipelineService
from app.core.task_manager import TaskManager
from app.core.theme_service import ThemeService
from app.core.translation_router import TranslationConfig, TranslationRouter
from app.core.ytdlp_service import YtDlpService
from app.infra.config_store import AppConfig, ConfigStore
from app.ui import design_tokens as dt
from app.ui.download_panel import DownloadPanel
from app.ui.merge_panel import MergePanel
from app.ui.settings_panel import SettingsPanel
from app.ui.subtitle_panel import SubtitlePanel
from app.ui.widgets.frosted_card import FrostedCard
from app.ui.widgets.segmented_nav import SegmentedNavBar
from app.version import __version__


class MainWindow(QMainWindow):
    def __init__(self, cfg_store: ConfigStore) -> None:
        super().__init__()
        self.cfg_store = cfg_store
        self.config: AppConfig = cfg_store.load()
        self.i18n = I18N(self.config.language)

        self.theme_service = ThemeService()
        self.ffmpeg_service = FFmpegService(self.config.ffmpeg_path, self.config.ffprobe_path)
        self.subtitle_pipeline = SubtitlePipelineService(self.config.ffmpeg_path)
        self.translation_router = TranslationRouter()
        self.ytdlp_service = YtDlpService()
        self.task_manager = TaskManager(download_concurrency=self.config.max_download_concurrency)
        self.task_manager.subscribe(self._on_task_update)

        self._last_merge_task_id = ""
        self._last_download_task_id = ""
        self._last_subtitle_task_id = ""
        self._paused_download_payload: DownloadInput | None = None
        self._download_started_at: dict[str, float] = {}
        self._pause_tip_shown_merge = False
        self._pause_tip_shown_download = False

        self._blur_throttle_timer = QTimer(self)
        self._blur_throttle_timer.setSingleShot(True)
        self._blur_throttle_timer.timeout.connect(self._on_blur_tick)
        self._last_overlay_alpha = -1
        self._last_bg_path = ""
        self._bg_source = QPixmap()
        self._bg_scaled = QPixmap()
        self._pending_blur_radius = int(self.config.background_blur)
        self._blur_animation: QPropertyAnimation | None = None

        screen = QGuiApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            width = min(1200, max(980, g.width() - 140))
            height = min(760, max(640, g.height() - 140))
            self.resize(width, height)
        else:
            self.resize(1080, 700)
        self.setMinimumSize(940, 620)

        dt.CONTENT_MAX_WIDTH = int(self.config.ui_content_width)
        if int(self.config.ui_label_width) > 108:
            self.config.ui_label_width = 108
            self.cfg_store.save(self.config)
        dt.LABEL_WIDTH = int(self.config.ui_label_width)

        self._build_ui()
        self.i18n.subscribe(self.retranslate_ui)
        self.retranslate_ui()

        self._load_background_source()
        self._update_background_scaled_cache()
        self._apply_overlay_alpha(int(self.config.overlay_opacity * 255))

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)

        self.bg_label = QLabel(root)
        self.bg_label.setScaledContents(False)
        self.bg_label.lower()
        self.bg_effect = QGraphicsBlurEffect(self.bg_label)
        self.bg_effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint | QGraphicsBlurEffect.BlurHint.AnimationHint)
        self.bg_label.setGraphicsEffect(self.bg_effect)
        self.bg_effect.setBlurRadius(float(self.config.background_blur))

        wrapper = QVBoxLayout(root)
        wrapper.setContentsMargins(20, 18, 20, 18)
        wrapper.setSpacing(10)

        self.root_card = FrostedCard(root)
        self.root_card.setObjectName("MainCard")
        self.root_card.layout.setContentsMargins(14, 14, 14, 14)
        self.root_card.layout.setSpacing(10)
        wrapper.addWidget(self.root_card, 1)

        self.nav = SegmentedNavBar(["", "", "", ""], self._on_nav_change)
        self.root_card.layout.addWidget(self.nav, 0)

        self.stack = QStackedWidget()
        self.stack.setObjectName("MainStack")
        self.root_card.layout.addWidget(self.stack, 1)

        self.merge_panel = MergePanel(self.i18n, self._submit_merge, self._cancel_merge, self._toggle_merge_pause)
        self.download_panel = DownloadPanel(
            self.i18n,
            self._fetch_formats,
            self._submit_download,
            self._cancel_download,
            self._toggle_download_pause,
        )
        self.subtitle_panel = SubtitlePanel(
            self.i18n,
            self._submit_subtitle,
            self._download_model,
            self._warmup_model,
            self._unload_model,
            self._test_asr_connection,
            self._test_translation_connection,
        )
        self.settings_panel = SettingsPanel(
            self.i18n,
            self._pick_background,
            self._reset_background,
            self._pick_preview_image,
            self._reset_preview_image,
            self._save_ffmpeg_paths,
            self._on_language_change,
            self._run_environment_check,
            __version__,
        )

        self.stack.addWidget(self.merge_panel)
        self.stack.addWidget(self.download_panel)
        self.stack.addWidget(self.subtitle_panel)
        self.stack.addWidget(self.settings_panel)

        self.settings_panel.set_ffmpeg_paths(self.config.ffmpeg_path, self.config.ffprobe_path)
        self.settings_panel.set_language(self.i18n.language)
        self.settings_panel.blur_slider.setValue(self.config.background_blur)
        self.settings_panel.opacity_slider.setValue(int(self.config.overlay_opacity * 100))
        if self.config.preview_image_1_path and Path(self.config.preview_image_1_path).exists():
            self.settings_panel.set_preview_image(1, self.config.preview_image_1_path)
        if self.config.preview_image_2_path and Path(self.config.preview_image_2_path).exists():
            self.settings_panel.set_preview_image(2, self.config.preview_image_2_path)
        self.download_panel.apply_defaults(
            output_dir=self.config.download_output_dir,
            cookie_mode=self.config.cookie_mode_default,
            browser=self.config.browser_default,
        )
        self.subtitle_panel.apply_defaults(
            model_dir=self.config.subtitle_model_dir,
            profile=self.config.translator_profiles.get(self.config.active_translator_profile, {}),
            compute_preference=self.config.subtitle_compute_preference,
            auto_unload_after_asr=self.config.subtitle_auto_unload_after_asr,
        )
        self.merge_panel.apply_saved_state(self.config.merge_form_state)
        self.download_panel.apply_saved_state(self.config.download_form_state)
        self.subtitle_panel.apply_saved_state(self.config.subtitle_form_state)

        self.settings_panel.blur_slider.valueChanged.connect(self._on_blur_changed)
        self.settings_panel.opacity_slider.valueChanged.connect(self._on_opacity_changed)

        self.nav.set_current(0)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        assert self.merge_panel.submit_btn is not None
        assert self.download_panel.download_btn is not None
        assert self.subtitle_panel.start_btn is not None

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_form_states()
        super().closeEvent(event)

    def _save_form_states(self) -> None:
        self.config.merge_form_state = self.merge_panel.export_state()
        self.config.download_form_state = self.download_panel.export_state()
        self.config.subtitle_form_state = self.subtitle_panel.export_state()

        dl_dir = str(self.config.download_form_state.get("output_dir", "") or "").strip()
        if dl_dir:
            self.config.download_output_dir = dl_dir
        merge_out = str(self.config.merge_form_state.get("output_path", "") or "").strip()
        if merge_out:
            try:
                self.config.merge_output_dir = str(Path(merge_out).parent)
            except Exception:
                pass
        self.cfg_store.save(self.config)

    def eventFilter(self, obj: QObject, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel:
            current: QObject | None = obj if isinstance(obj, QObject) else None
            while current is not None:
                if isinstance(current, QComboBox):
                    if not current.view().isVisible():
                        self._scroll_parent_area(current, event)
                        return True
                    break
                if isinstance(current, QAbstractSpinBox):
                    self._scroll_parent_area(current, event)
                    return True
                current = current.parent()
        return super().eventFilter(obj, event)

    @staticmethod
    def _scroll_parent_area(start: QObject, event) -> None:
        parent = start.parent()
        while parent is not None:
            if isinstance(parent, QAbstractScrollArea):
                bar = parent.verticalScrollBar()
                if bar is None:
                    return
                dy = event.angleDelta().y()
                if dy == 0:
                    dy = event.pixelDelta().y()
                if dy == 0:
                    return
                steps = dy / 120.0
                delta = int(steps * max(24, bar.singleStep() * 3))
                bar.setValue(bar.value() - delta)
                return
            parent = parent.parent()

    def _on_nav_change(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

    def retranslate_ui(self) -> None:
        self.setWindowTitle(self.i18n.t("app.title"))
        self.nav.set_items(
            [
                self.i18n.t("tab.merge"),
                self.i18n.t("tab.download"),
                self.i18n.t("tab.subtitle"),
                self.i18n.t("tab.settings"),
            ]
        )

    def _on_language_change(self, language: str) -> None:
        self.config.language = language
        self.cfg_store.save(self.config)
        self.i18n.set_language(language)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "bg_label"):
            self.bg_label.setGeometry(self.rect())
            self._update_background_scaled_cache()

    def _load_background_source(self) -> None:
        path = self.config.background_image_path if self.config.background_image_path and Path(self.config.background_image_path).exists() else ""
        if path != self._last_bg_path:
            self._last_bg_path = path
            self._bg_source = QPixmap(path) if path else QPixmap()

    def _update_background_scaled_cache(self) -> None:
        if not self._bg_source.isNull():
            self._bg_scaled = self._bg_source.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.bg_label.setPixmap(self._bg_scaled)
        else:
            self._bg_scaled = QPixmap()
            self.bg_label.setPixmap(QPixmap())

    def _animate_blur_to(self, radius: int) -> None:
        radius = max(0, radius)
        if self._blur_animation is not None:
            self._blur_animation.stop()
        self._blur_animation = QPropertyAnimation(self.bg_effect, b"blurRadius", self)
        self._blur_animation.setDuration(max(80, int(self.config.blur_animation_ms)))
        self._blur_animation.setStartValue(self.bg_effect.blurRadius())
        self._blur_animation.setEndValue(float(radius))
        self._blur_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._blur_animation.start()

    def _apply_overlay_alpha(self, alpha: int) -> None:
        clamped = max(120, min(240, int(alpha)))
        if clamped == self._last_overlay_alpha:
            return
        self._last_overlay_alpha = clamped
        dark_alpha = int(clamped * 0.78)
        self.root_card.setStyleSheet(
            f"#MainCard {{ background: rgba(18, 24, 33, {dark_alpha}); border-radius: 20px; border: 1px solid rgba(255,255,255,80); }}"
        )
        self.stack.setStyleSheet("#MainStack { background: transparent; border: none; }")

    def _save_ffmpeg_paths(self, ffmpeg: str, ffprobe: str) -> None:
        if not (ffmpeg and ffprobe):
            QMessageBox.warning(self, "Error", "Set both ffmpeg and ffprobe.")
            return
        self.config.ffmpeg_path = ffmpeg
        self.config.ffprobe_path = ffprobe
        self.cfg_store.save(self.config)
        self.ffmpeg_service = FFmpegService(ffmpeg, ffprobe)
        self.subtitle_pipeline = SubtitlePipelineService(ffmpeg)

    def _pick_background(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.i18n.t("settings.background"), "", "Image (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        imported = self.theme_service.import_background(path)
        self.config.background_image_path = imported
        self.cfg_store.save(self.config)
        self._load_background_source()
        self._update_background_scaled_cache()

    def _reset_background(self) -> None:
        self.config.background_image_path = ""
        self.cfg_store.save(self.config)
        self._load_background_source()
        self._update_background_scaled_cache()

    def _pick_preview_image(self, slot: int) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.i18n.t("common.select"), "", "Image (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        imported = self.theme_service.import_preview_image(path, slot)
        if slot == 1:
            self.config.preview_image_1_path = imported
        else:
            self.config.preview_image_2_path = imported
        self.cfg_store.save(self.config)
        self.settings_panel.set_preview_image(slot, imported)

    def _reset_preview_image(self, slot: int) -> None:
        if slot == 1:
            self.config.preview_image_1_path = ""
        else:
            self.config.preview_image_2_path = ""
        self.settings_panel.clear_preview_image(slot)
        self.cfg_store.save(self.config)

    def _on_blur_changed(self, value: int) -> None:
        self.config.background_blur = value
        self.cfg_store.save(self.config)
        self._pending_blur_radius = int(value)
        self._blur_throttle_timer.start(16)

    def _on_blur_tick(self) -> None:
        self._animate_blur_to(self._pending_blur_radius)

    def _on_opacity_changed(self, value: int) -> None:
        self.config.overlay_opacity = float(value) / 100.0
        self.cfg_store.save(self.config)
        self._apply_overlay_alpha(int(self.config.overlay_opacity * 255))

    def _run_environment_check(self) -> None:
        results: dict[str, str] = {}
        missing: list[str] = []

        ffmpeg_ok = False
        ffprobe_ok = False
        if self.config.ffmpeg_path and Path(self.config.ffmpeg_path).exists():
            try:
                proc = subprocess.run(
                    [self.config.ffmpeg_path, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                ffmpeg_ok = True
                first = (proc.stdout or "").splitlines()
                results["ffmpeg"] = first[0].strip() if first else "OK"
            except Exception:
                ffmpeg_ok = False
        if not ffmpeg_ok:
            results["ffmpeg"] = "Missing or invalid"
        if self.config.ffprobe_path and Path(self.config.ffprobe_path).exists():
            try:
                proc = subprocess.run(
                    [self.config.ffprobe_path, "-version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                ffprobe_ok = True
                first = (proc.stdout or "").splitlines()
                results["ffprobe"] = first[0].strip() if first else "OK"
            except Exception:
                ffprobe_ok = False
        if not ffprobe_ok:
            results["ffprobe"] = "Missing or invalid"
        if not ffmpeg_ok:
            missing.append("ffmpeg")
        if not ffprobe_ok:
            missing.append("ffprobe")

        try:
            results["yt-dlp"] = self.ytdlp_service.check_version()
        except Exception:
            results["yt-dlp"] = "Missing or invalid"
            missing.append("yt-dlp")

        if importlib.util.find_spec("faster_whisper") is None:
            results["faster-whisper"] = "Missing"
            missing.append("faster-whisper")
        else:
            try:
                results["faster-whisper"] = importlib.metadata.version("faster-whisper")
            except Exception:
                results["faster-whisper"] = "Installed"

        cuda_ok, cuda_info = self._detect_cuda_info()
        if not cuda_ok:
            missing.append("CUDA")
            results["CUDA"] = cuda_info
        else:
            results["CUDA"] = cuda_info

        fw_diag = self.subtitle_pipeline.asr.diagnose_gpu_stack()
        results["ctranslate2"] = fw_diag.get("ctranslate2", "unknown")
        cuda_lib_ok = fw_diag.get("cublas64_12.dll") == "ok" and fw_diag.get("cudnn64_9.dll") == "ok"
        cublas_ver = fw_diag.get("nvidia-cublas-cu12", "")
        cudnn_ver = fw_diag.get("nvidia-cudnn-cu12", "")
        cublas_part = f"cublas64_12={fw_diag.get('cublas64_12.dll','?')}"
        cudnn_part = f"cudnn64_9={fw_diag.get('cudnn64_9.dll','?')}"
        if cublas_ver:
            cublas_part += f" (pkg {cublas_ver})"
        if cudnn_ver:
            cudnn_part += f" (pkg {cudnn_ver})"
        elif fw_diag.get("cudnn64_9.dll") == "ok":
            cudnn_part += " (bundled)"
        results["FW CUDA libs"] = (
            f"{cublas_part}, "
            f"{cudnn_part}, "
            f"gpu_count={fw_diag.get('gpu_count','0')}"
        )
        if fw_diag.get("cublas64_12.dll_detail"):
            results["FW cublas detail"] = fw_diag.get("cublas64_12.dll_detail", "")
        if fw_diag.get("cudnn64_9.dll_detail"):
            results["FW cudnn detail"] = fw_diag.get("cudnn64_9.dll_detail", "")
        if not cuda_lib_ok:
            missing.append("FW CUDA libs")

        if missing:
            self._show_env_result_dialog(ok=False, results=results, missing=missing)
            return

        self._show_env_result_dialog(ok=True, results=results, missing=[])

    @staticmethod
    def _detect_cuda_info() -> tuple[bool, str]:
        try:
            proc = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=6, check=False)
            output = (proc.stdout or "") + "\n" + (proc.stderr or "")
            cuda_match = re.search(r"CUDA Version:\s*([0-9.]+)", output)
            drv_match = re.search(r"Driver Version:\s*([0-9.]+)", output)
            if cuda_match:
                cuda_ver = cuda_match.group(1)
                if drv_match:
                    return True, f"{cuda_ver} (driver {drv_match.group(1)})"
                return True, cuda_ver
        except Exception:
            pass

        # Fallback: detect CUDA-capable runtime via ctranslate2 even when nvidia-smi is unavailable.
        try:
            import ctranslate2  # type: ignore

            if int(ctranslate2.get_cuda_device_count()) > 0:
                return True, "Available"
        except Exception:
            pass
        return False, "Unavailable"

    def _show_env_result_dialog(self, ok: bool, results: dict[str, str], missing: list[str]) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(self.i18n.t("settings.env_ok_title") if ok else self.i18n.t("settings.env_missing_title"))
        dlg.setMinimumWidth(560)
        dlg.setMinimumHeight(340)
        dlg.setStyleSheet(
            """
            QDialog { background: #f3f4f6; }
            QLabel { color: #0f172a; background: transparent; font-size: 14px; }
            QLabel#EnvStatusTitle { color: #0f172a; font-size: 16px; font-weight: 700; }
            QDialogButtonBox QPushButton {
              min-width: 84px;
              color: #0f172a;
              background: #e5e7eb;
              border: 1px solid #cbd5e1;
              border-radius: 8px;
              padding: 6px 10px;
            }
            QDialogButtonBox QPushButton:hover { background: #dbe0e8; }
            """
        )

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        status = QLabel(self.i18n.t("settings.env_ok_message") if ok else self.i18n.t("settings.env_missing_message"))
        status.setObjectName("EnvStatusTitle")
        layout.addWidget(status)
        if not ok and "FW CUDA libs" in missing:
            tip = QLabel(self.i18n.t("settings.env_fw_tip"))
            tip.setStyleSheet("color:#b45309;")
            tip.setWordWrap(True)
            layout.addWidget(tip)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(8)
        name_w = 130
        fields = ["ffmpeg", "ffprobe", "yt-dlp", "faster-whisper", "ctranslate2", "CUDA", "FW CUDA libs"]
        if results.get("FW cublas detail"):
            fields.append("FW cublas detail")
        if results.get("FW cudnn detail"):
            fields.append("FW cudnn detail")
        for name in fields:
            key = QLabel(f"{name}:")
            key.setMinimumWidth(name_w)
            value = QLabel(results.get(name, ""))
            value.setWordWrap(True)
            if name in missing:
                value.setStyleSheet("color:#fca5a5;")
            form.addRow(key, value)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dlg)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.exec()

    def _cancel_merge(self) -> None:
        if self._last_merge_task_id:
            self.task_manager.cancel(self._last_merge_task_id)
            self.merge_panel.pause_btn.setText(self.i18n.t("common.pause_task"))
            self.merge_panel.set_task_state("idle")

    def _cancel_download(self) -> None:
        if self._last_download_task_id:
            self.task_manager.cancel(self._last_download_task_id)
            self.download_panel.set_pause_state(False)
            self._paused_download_payload = None

    def _toggle_merge_pause(self) -> None:
        if not self._last_merge_task_id:
            return
        if not self._pause_tip_shown_merge:
            QMessageBox.information(self, "Pause", "FFmpeg pause/resume is generally safe for local processing.")
            self._pause_tip_shown_merge = True
        asyncio.create_task(self._toggle_merge_pause_async())

    async def _toggle_merge_pause_async(self) -> None:
        state = await self.ffmpeg_service.toggle_pause()
        if state is None:
            return
        if state:
            self.task_manager.set_status(self._last_merge_task_id, TaskStatus.PAUSED, "Paused")
            self.merge_panel.pause_btn.setText(self.i18n.t("common.resume_task"))
            self.merge_panel.set_task_state("paused")
        else:
            self.task_manager.set_status(self._last_merge_task_id, TaskStatus.RUNNING, "Running")
            self.merge_panel.pause_btn.setText(self.i18n.t("common.pause_task"))
            self.merge_panel.set_task_state("running")

    def _toggle_download_pause(self) -> None:
        rec = self.task_manager.get(self._last_download_task_id) if self._last_download_task_id else None
        if rec and rec.status == TaskStatus.RUNNING:
            if not self._pause_tip_shown_download:
                QMessageBox.information(self, "Pause", "Download pause uses stop and later resume (continuedl).")
                self._pause_tip_shown_download = True
            self._paused_download_payload = rec.payload if isinstance(rec.payload, DownloadInput) else None
            self.task_manager.cancel(self._last_download_task_id, reason="pause")
            self.download_panel.set_pause_state(True)
            self.download_panel.set_live_log("下载已暂停，可继续断点续传。")
            return
        if self._paused_download_payload:
            self.download_panel.set_live_log("继续下载中...")
            self._submit_download(self._paused_download_payload)
            self.download_panel.set_pause_state(False)

    def _submit_merge(self, payload: MergeInput) -> None:
        async def runner(rec):
            all_inputs = payload.visual_paths + payload.image_paths + payload.audio_paths + payload.subtitle_paths
            probes = await asyncio.gather(*(self.ffmpeg_service.probe(p) for p in all_inputs))
            metas = {m.path: m for m in probes}
            expected = self._expected_merge_duration(payload, metas)

            def progress(ev: dict) -> None:
                percent = self._merge_progress_percent(ev, expected)
                msg = str(ev.get("status", "")) or str(ev)
                self.task_manager.update_progress(rec.task_id, percent, msg)
                self.merge_panel.set_progress(percent, msg)

            result, final_path = await self.ffmpeg_service.merge(payload, metas, progress_cb=progress)
            if not result.ok:
                raise RuntimeError(result.message)
            return {"output_path": final_path}

        task_id = self.task_manager.submit(TaskType.MERGE, payload, runner)
        self._last_merge_task_id = task_id
        self.merge_panel.append_log(f"[{task_id}] queued")
        self.merge_panel.set_task_state("running")

    def _fetch_formats(self, payload: DownloadInput) -> None:
        async def _run() -> None:
            try:
                formats = await self.ytdlp_service.list_formats(payload.url, payload)
                options = self.ytdlp_service.build_quality_options(formats)
                self.download_panel.set_formats(options)
                self.download_panel.append_log("Quality list loaded.")
            except Exception as exc:  # noqa: BLE001
                self.download_panel.append_log(f"Failed to load qualities: {exc}")
                QMessageBox.warning(self, "Quality", str(exc))

        asyncio.create_task(_run())

    def _submit_download(self, payload: DownloadInput) -> None:
        async def runner(rec):
            loop = asyncio.get_running_loop()
            started_at = perf_counter()
            self._download_started_at[rec.task_id] = started_at

            def progress(ev: dict) -> None:
                percent = 0.0
                total = ev.get("total_bytes") or ev.get("total_bytes_estimate")
                done = ev.get("downloaded_bytes")
                if total and done:
                    percent = float(done) / float(total) * 100.0
                status = str(ev.get("status") or "")
                speed = ev.get("speed")
                eta = ev.get("eta")
                elapsed = perf_counter() - started_at
                if status == "finished":
                    percent = 100.0
                msg = self._format_download_status_line(
                    status=status,
                    percent=percent,
                    done_bytes=done,
                    total_bytes=total,
                    speed=speed,
                    eta=eta,
                    elapsed=elapsed,
                )
                loop.call_soon_threadsafe(self._on_download_progress, rec.task_id, percent, str(msg))

            try:
                result = await self.ytdlp_service.download(payload, progress_cb=progress)
                elapsed = perf_counter() - started_at
                return {"filepath": result.filepath, "title": result.title, "elapsed_seconds": elapsed}
            finally:
                self._download_started_at.pop(rec.task_id, None)

        task_id = self.task_manager.submit(TaskType.DOWNLOAD, payload, runner)
        self._last_download_task_id = task_id
        self.download_panel.set_live_log(f"[{task_id}] queued")
        self.download_panel.set_pause_state(False)

    def _download_model(self, model_name: str, model_dir: str | None, compute_preference: str = "auto") -> None:
        async def _run() -> None:
            begin = perf_counter()
            self.subtitle_panel.set_model_action_running(True)
            self.subtitle_panel.set_progress(0.0, f"Preparing model download: {model_name}")
            loop = asyncio.get_running_loop()
            last_logged: dict[str, str] = {"msg": ""}

            def on_progress(ev: dict) -> None:
                def _ui_apply() -> None:
                    pct = float(ev.get("progress", 0.0))
                    msg = str(ev.get("message", ""))
                    self.subtitle_panel.set_progress(pct, msg)
                    transient = bool(ev.get("transient", False))
                    if msg and (not transient) and msg != last_logged["msg"]:
                        self.subtitle_panel.append_log(msg)
                        last_logged["msg"] = msg

                loop.call_soon_threadsafe(_ui_apply)

            try:
                info = await self.subtitle_pipeline.download_model(
                    model_name,
                    model_dir,
                    compute_preference,
                    progress_cb=on_progress,
                )
                src = str(info.get("source", ""))
                skipped = bool(info.get("skipped", False))
                if src:
                    self.subtitle_panel.append_log(f"Model source: {src}")
                if skipped:
                    self.subtitle_panel.append_log(f"Model already exists locally, skip download: {model_name}")
                    self.subtitle_panel.set_progress(0.0, f"Model exists locally: {model_name}")
                    QMessageBox.information(self, "Model", f"Model already exists locally:\n{model_name}\n\nSkipped re-download.")
                else:
                    self.subtitle_panel.set_progress(100.0, f"Download complete: {model_name}")
                    QMessageBox.information(self, "Model", f"Model downloaded successfully: {model_name}")
                elapsed = 0.0 if skipped else (perf_counter() - begin)
                self.subtitle_panel.append_log(
                    f"{self.i18n.t('subtitle.elapsed.download_model')}: {self._format_elapsed(elapsed)}"
                )
            except Exception as exc:  # noqa: BLE001
                self.subtitle_panel.append_log(f"Model download failed: {exc}")
                self.subtitle_panel.set_progress(0.0, f"Download failed: {model_name}")
                QMessageBox.warning(self, "Model", f"Model download failed:\n{exc}")
            finally:
                self.subtitle_panel.set_model_action_running(False)

        self.config.subtitle_model_dir = model_dir or self.config.subtitle_model_dir
        self.config.subtitle_compute_preference = compute_preference if compute_preference in {"auto", "float16", "int8"} else "auto"
        self.cfg_store.save(self.config)
        asyncio.create_task(_run())

    def _warmup_model(self, model_name: str, model_dir: str | None, compute_preference: str = "auto") -> None:
        async def _run() -> None:
            begin = perf_counter()
            self.subtitle_panel.set_model_action_running(True)
            self.subtitle_panel.set_progress(0.0, f"Preheating model: {model_name}")
            loop = asyncio.get_running_loop()
            last_logged: dict[str, str] = {"msg": ""}

            def on_progress(ev: dict) -> None:
                def _ui_apply() -> None:
                    pct = float(ev.get("progress", 0.0))
                    msg = str(ev.get("message", ""))
                    self.subtitle_panel.set_progress(pct, msg)
                    transient = bool(ev.get("transient", False))
                    if msg and (not transient) and msg != last_logged["msg"]:
                        self.subtitle_panel.append_log(msg)
                        last_logged["msg"] = msg

                loop.call_soon_threadsafe(_ui_apply)

            try:
                await self.subtitle_pipeline.warmup_model(
                    model_name,
                    model_dir,
                    compute_preference,
                    progress_cb=on_progress,
                )
                self.subtitle_panel.set_progress(100.0, f"Model loaded: {model_name}")
                self.subtitle_panel.append_log(f"Model preheat finished: {model_name}")
                elapsed = perf_counter() - begin
                self.subtitle_panel.append_log(
                    f"{self.i18n.t('subtitle.elapsed.warmup_model')}: {self._format_elapsed(elapsed)}"
                )
                QMessageBox.information(self, "Model", f"Model loaded successfully: {model_name}")
            except Exception as exc:  # noqa: BLE001
                self.subtitle_panel.append_log(f"Model prepare failed: {exc}")
                self.subtitle_panel.set_progress(0.0, f"Preheat failed: {model_name}")
                QMessageBox.warning(
                    self,
                    "Model",
                    f"Model preheat failed.\nPlease download model first or check model directory.\n\n{exc}",
                )
            finally:
                self.subtitle_panel.set_model_action_running(False)

        self.config.subtitle_model_dir = model_dir or self.config.subtitle_model_dir
        self.config.subtitle_compute_preference = compute_preference if compute_preference in {"auto", "float16", "int8"} else "auto"
        self.cfg_store.save(self.config)
        asyncio.create_task(_run())

    def _unload_model(self) -> None:
        async def _run() -> None:
            self.subtitle_panel.set_model_action_running(True)
            try:
                await self.subtitle_pipeline.unload_model()
                self.subtitle_panel.append_log("ASR model unloaded from memory.")
                self.subtitle_panel.set_progress(0.0, "Model unloaded")
                QMessageBox.information(self, "Model", "ASR model unloaded from memory.")
            except Exception as exc:  # noqa: BLE001
                self.subtitle_panel.append_log(f"Unload model failed: {exc}")
                QMessageBox.warning(self, "Model", f"Unload model failed:\n{exc}")
            finally:
                self.subtitle_panel.set_model_action_running(False)

        asyncio.create_task(_run())

    def _test_translation_connection(self, payload: SubtitleJobInput) -> None:
        payload = self._resolve_subtitle_payload(payload)
        cfg = TranslationConfig(
            provider=payload.translator_provider,
            base_url=payload.api_base_url,
            api_key=payload.api_key,
            model_name=payload.model_name,
            extra_headers=payload.extra_headers,
        )
        ok, msg = self.translation_router.test_connection(cfg)
        self.subtitle_panel.append_log(f"Connection test: {'OK' if ok else 'FAIL'} {msg}")
        if not ok:
            QMessageBox.warning(self, "Connection", msg)

    def _test_asr_connection(self, payload: SubtitleJobInput) -> None:
        payload = self._resolve_subtitle_payload(payload)
        if payload.asr_backend == "faster_whisper":
            self.subtitle_panel.append_log("ASR connection test: local backend does not require API probing.")
            return

        async def _run() -> None:
            self.subtitle_panel.append_log("ASR connection test: running...")
            ok, msg = await self.subtitle_pipeline.asr.test_cloud_asr_connection(
                api_base_url=payload.asr_api_base_url or "",
                api_key=payload.asr_api_key or "",
                model_name=payload.asr_model_name or "",
                backend=payload.asr_backend,
            )
            self.subtitle_panel.append_log(f"ASR connection test: {'OK' if ok else 'FAIL'} {msg}")
            if not ok:
                QMessageBox.warning(self, "ASR Connection", msg)

        asyncio.create_task(_run())

    def _submit_subtitle(self, payload: SubtitleJobInput, mode: str = "all") -> None:
        payload = self._resolve_subtitle_payload(payload)
        payload.run_mode = mode  # type: ignore[assignment]
        self.config.subtitle_model_dir = payload.model_dir or self.config.subtitle_model_dir
        self.config.subtitle_compute_preference = payload.asr_compute_type
        self.config.subtitle_auto_unload_after_asr = payload.auto_unload_after_asr
        self.cfg_store.save(self.config)

        async def runner(rec):
            loop = asyncio.get_running_loop()

            def apply_progress(ev: dict) -> None:
                pct = float(ev.get("progress", 0.0))
                msg = str(ev.get("message", ""))
                self.task_manager.update_progress(rec.task_id, pct, msg)
                self.subtitle_panel.set_progress(pct, msg)

            def progress(ev: dict) -> None:
                loop.call_soon_threadsafe(apply_progress, ev)

            out = await self.subtitle_pipeline.run(payload, progress_cb=progress)
            self.subtitle_panel.set_progress(100.0, "Done")
            timings = out.get("timings", {}) if isinstance(out, dict) else {}
            if isinstance(timings, dict):
                if isinstance(timings.get("asr_seconds"), (int, float)):
                    self.subtitle_panel.append_log(
                        f"{self.i18n.t('subtitle.elapsed.asr')}: {self._format_elapsed(float(timings['asr_seconds']))}"
                    )
                if isinstance(timings.get("auto_unload_seconds"), (int, float)):
                    self.subtitle_panel.append_log(
                        f"{self.i18n.t('subtitle.elapsed.auto_unload')}: {self._format_elapsed(float(timings['auto_unload_seconds']))}"
                    )
                if isinstance(timings.get("translate_seconds"), (int, float)):
                    self.subtitle_panel.append_log(
                        f"{self.i18n.t('subtitle.elapsed.translate')}: {self._format_elapsed(float(timings['translate_seconds']))}"
                    )
                if isinstance(timings.get("mux_seconds"), (int, float)):
                    self.subtitle_panel.append_log(
                        f"{self.i18n.t('subtitle.elapsed.mux')}: {self._format_elapsed(float(timings['mux_seconds']))}"
                    )
                if mode == "all" and isinstance(timings.get("total_seconds"), (int, float)):
                    self.subtitle_panel.append_log(
                        f"{self.i18n.t('subtitle.elapsed.total')}: {self._format_elapsed(float(timings['total_seconds']))}"
                    )
            if out.get("raw_srt"):
                self.subtitle_panel.append_log(f"Raw subtitle: {out['raw_srt']}")
            if out.get("translated_srt"):
                self.subtitle_panel.append_log(f"Translated subtitle: {out['translated_srt']}")
            if out.get("output_video"):
                self.subtitle_panel.append_log(f"Output video: {out['output_video']}")
            return out

        task_id = self.task_manager.submit(TaskType.SUBTITLE, payload, runner)
        self._last_subtitle_task_id = task_id
        self.subtitle_panel.append_log(f"[{task_id}] queued")

    def _resolve_subtitle_payload(self, payload: SubtitleJobInput) -> SubtitleJobInput:
        profile_name = payload.translator_provider if payload.translator_provider in self.config.translator_profiles else "custom"
        profile = self.config.translator_profiles.get(profile_name, {})

        base_url = payload.api_base_url or profile.get("base_url")
        model_name = payload.model_name or profile.get("model", "gpt-4o-mini")
        provider = payload.translator_provider

        self.config.active_translator_profile = profile_name
        self.config.translator_profiles[profile_name] = {
            "provider": provider,
            "base_url": base_url or "",
            "model": model_name,
        }
        self.cfg_store.save(self.config)

        return SubtitleJobInput(
            video_path=payload.video_path,
            output_dir=payload.output_dir,
            preset_mode=payload.preset_mode,
            voice_image_path=payload.voice_image_path,
            voice_audio_path=payload.voice_audio_path,
            voice_subtitle_path=payload.voice_subtitle_path,
            voice_output_container=payload.voice_output_container,
            voice_output_quality=payload.voice_output_quality,
            voice_subtitle_mode=payload.voice_subtitle_mode,
            asr_backend=payload.asr_backend,
            whisper_model=payload.whisper_model,
            asr_compute_type=payload.asr_compute_type,
            model_dir=payload.model_dir,
            asr_api_base_url=payload.asr_api_base_url,
            asr_api_key=payload.asr_api_key,
            asr_model_name=payload.asr_model_name,
            source_lang=payload.source_lang,
            target_lang=payload.target_lang,
            translator_provider=provider,
            api_base_url=base_url,
            api_key=payload.api_key,
            model_name=model_name,
            extra_headers=payload.extra_headers,
            auto_unload_after_asr=payload.auto_unload_after_asr,
            run_mode=payload.run_mode,
        )

    def _on_download_progress(self, task_id: str, percent: float, message: str) -> None:
        self.task_manager.update_progress(task_id, percent, message)
        self.download_panel.set_progress(percent)

    def _on_task_update(self, rec) -> None:
        if rec.task_type == TaskType.MERGE:
            self.merge_panel.append_log(f"{rec.status.value}: {rec.message}")
            if rec.status == TaskStatus.RUNNING:
                self.merge_panel.set_task_state("running")
            if rec.status == TaskStatus.PAUSED:
                self.merge_panel.set_task_state("paused")
            if rec.status == TaskStatus.SUCCESS:
                self.merge_panel.clear_inputs_after_success()
                out = rec.result.get("output_path", "")
                if out:
                    self.merge_panel.append_log(f"Output: {out}")
                self.merge_panel.set_task_state("success")
            if rec.status == TaskStatus.FAILED:
                self.merge_panel.set_task_state("failed")
            if rec.status == TaskStatus.CANCELED:
                self.merge_panel.set_task_state("idle")
        elif rec.task_type == TaskType.DOWNLOAD:
            if rec.status == TaskStatus.QUEUED:
                self.download_panel.set_live_log(f"[{rec.task_id}] queued")
            elif rec.status == TaskStatus.RUNNING:
                if rec.message:
                    self.download_panel.set_live_log(self._sanitize_download_text(rec.message))
            elif rec.status == TaskStatus.PAUSED:
                elapsed = self._format_elapsed(perf_counter() - self._download_started_at.get(rec.task_id, perf_counter()))
                self.download_panel.set_live_log(f"下载已暂停 | 耗时 {elapsed}")
                self.download_panel.set_pause_state(True)
                self._download_started_at.pop(rec.task_id, None)
            elif rec.status == TaskStatus.SUCCESS:
                elapsed_seconds = 0.0
                if isinstance(rec.result, dict):
                    raw_elapsed = rec.result.get("elapsed_seconds")
                    if isinstance(raw_elapsed, (int, float)):
                        elapsed_seconds = float(raw_elapsed)
                if elapsed_seconds <= 0 and rec.task_id in self._download_started_at:
                    elapsed_seconds = perf_counter() - self._download_started_at[rec.task_id]
                filename = ""
                if isinstance(rec.result, dict):
                    raw_path = rec.result.get("filepath")
                    if isinstance(raw_path, str) and raw_path:
                        filename = Path(raw_path).name
                suffix = f" | 文件 {filename}" if filename else ""
                self.download_panel.set_live_log(
                    f"下载完成 100.0% | 耗时 {self._format_elapsed(elapsed_seconds)}{suffix}"
                )
                self._download_started_at.pop(rec.task_id, None)
                self.download_panel.set_pause_state(False)
                self._paused_download_payload = None
            elif rec.status == TaskStatus.CANCELED:
                elapsed = self._format_elapsed(perf_counter() - self._download_started_at.get(rec.task_id, perf_counter()))
                self.download_panel.set_live_log(f"下载已取消 | 耗时 {elapsed}")
                self._download_started_at.pop(rec.task_id, None)
                self.download_panel.set_pause_state(False)
                self._paused_download_payload = None
            elif rec.status == TaskStatus.FAILED:
                msg = self._sanitize_download_text(rec.message)
                self.download_panel.set_live_log(f"下载失败 | {msg}" if msg else "下载失败")
                self._download_started_at.pop(rec.task_id, None)
                self.download_panel.set_pause_state(False)
                self._paused_download_payload = None
        elif rec.task_type == TaskType.SUBTITLE:
            self.subtitle_panel.append_log(f"{rec.status.value}: {rec.message}")
            if rec.status == TaskStatus.FAILED:
                self.subtitle_panel.set_progress(0, "Failed")

        if rec.status in {TaskStatus.FAILED, TaskStatus.CANCELED}:
            QMessageBox.warning(self, "Task", f"{rec.task_type.value} {rec.status.value}: {rec.message}")

    @staticmethod
    def _to_seconds(value: str) -> float:
        parts = value.split(":")
        if len(parts) != 3:
            return 0.0
        try:
            h = float(parts[0])
            m = float(parts[1])
            s = float(parts[2])
        except ValueError:
            return 0.0
        return h * 3600 + m * 60 + s

    def _expected_merge_duration(self, payload: MergeInput, metas: dict[str, object]) -> float | None:
        durations = []
        for path in payload.visual_paths + payload.image_paths + payload.audio_paths + payload.subtitle_paths:
            meta = metas.get(path)
            dur = getattr(meta, "duration", None)
            if dur:
                durations.append(float(dur))
        if not durations:
            return None
        if payload.sync_mode == "shortest":
            return min(durations)
        if payload.sync_mode == "audio" and payload.audio_paths:
            audios = [float(getattr(metas[p], "duration", 0.0)) for p in payload.audio_paths if p in metas and getattr(metas[p], "duration", None)]
            if audios:
                return max(audios)
        if payload.sync_mode == "video" and payload.visual_paths:
            videos = [float(getattr(metas[p], "duration", 0.0)) for p in payload.visual_paths if p in metas and getattr(metas[p], "duration", None)]
            if videos:
                return max(videos)
        return max(durations)

    def _merge_progress_percent(self, event: dict, expected_duration: float | None) -> float:
        if not expected_duration:
            return 0.0
        time_text = str(event.get("time", ""))
        if not time_text:
            return 0.0
        seconds = self._to_seconds(time_text)
        return min(100.0, (seconds / expected_duration) * 100.0)

    @staticmethod
    def _sanitize_download_text(text: str) -> str:
        if not text:
            return ""
        cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
        cleaned = cleaned.replace("\r", " ").replace("\n", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @staticmethod
    def _format_size_mib(value: object) -> str:
        if not isinstance(value, (int, float)):
            return "--"
        if value <= 0:
            return "--"
        return f"{float(value) / (1024 * 1024):.2f}MiB"

    def _format_download_status_line(
        self,
        *,
        status: str,
        percent: float,
        done_bytes: object,
        total_bytes: object,
        speed: object,
        eta: object,
        elapsed: float,
    ) -> str:
        elapsed_text = self._format_elapsed(elapsed)
        if status in {"downloading", "finished"}:
            pct_text = f"{max(0.0, min(100.0, percent)):0.1f}%"
            done_text = self._format_size_mib(done_bytes)
            total_text = self._format_size_mib(total_bytes)
            speed_text = "--"
            if isinstance(speed, (int, float)) and speed > 0:
                speed_text = f"{float(speed) / (1024 * 1024):.2f}MiB/s"
            eta_text = "--"
            if isinstance(eta, (int, float)) and eta >= 0:
                eta_text = self._format_elapsed(float(eta))
            stage = "下载中" if status == "downloading" else "收尾中"
            return (
                f"{stage} {pct_text} | "
                f"{done_text}/{total_text} | "
                f"{speed_text} | "
                f"ETA {eta_text} | "
                f"耗时 {elapsed_text}"
            )
        base = self._sanitize_download_text(status or "working")
        return f"{base} | 耗时 {elapsed_text}"

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        whole = int(seconds)
        ms = int((seconds - whole) * 1000)
        m, s = divmod(whole, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
        return f"{m:02d}:{s:02d}.{ms:03d}"
