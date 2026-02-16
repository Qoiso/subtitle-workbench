from __future__ import annotations

import json
from dataclasses import dataclass, asdict, fields
from pathlib import Path
from typing import Literal

from app.infra.paths import bundled_ffmpeg_path, bundled_ffprobe_path, config_path


@dataclass(slots=True)
class AppConfig:
    ffmpeg_path: str = str(bundled_ffmpeg_path())
    ffprobe_path: str = str(bundled_ffprobe_path())
    download_output_dir: str = str(Path.home() / "Downloads")
    merge_output_dir: str = str(Path.home() / "Videos")
    background_image_path: str = ""
    preview_image_1_path: str = ""
    preview_image_2_path: str = ""
    background_blur: int = 12
    overlay_opacity: float = 0.78
    default_container: str = "mkv"
    max_download_concurrency: int = 2
    cookie_mode_default: str = "none"
    browser_default: str = "chrome"
    language: str = "zh"
    subtitle_model_dir: str = str(Path.home() / ".cache" / "faster_whisper")
    subtitle_compute_preference: Literal["auto", "float16", "int8"] = "auto"
    subtitle_auto_unload_after_asr: bool = False
    translator_profiles: dict[str, dict[str, str]] = None  # type: ignore[assignment]
    active_translator_profile: str = "custom"
    ui_density: Literal["comfortable"] = "comfortable"
    ui_motion: Literal["light"] = "light"
    ui_content_width: int = 1040
    ui_label_width: int = 120
    blur_animation_ms: int = 120
    ui_nav_style: Literal["segmented"] = "segmented"
    ui_accent: Literal["mint"] = "mint"
    ui_log_drawer_collapsed: bool = True
    ui_single_glass: bool = True
    merge_form_state: dict[str, object] = None  # type: ignore[assignment]
    download_form_state: dict[str, object] = None  # type: ignore[assignment]
    subtitle_form_state: dict[str, object] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.translator_profiles is None:
            self.translator_profiles = {
                "openai": {"provider": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
                "qwen": {"provider": "qwen", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
                "deepseek": {"provider": "deepseek", "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
                "openrouter": {"provider": "openrouter", "base_url": "https://openrouter.ai/api/v1", "model": "google/gemini-2.0-flash-001"},
                "gemini_official": {"provider": "gemini_official", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "model": "gemini-2.5-flash"},
                "lmstudio": {"provider": "lmstudio", "base_url": "http://127.0.0.1:1234/v1", "model": "local-model"},
                "ollama": {"provider": "ollama", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:7b"},
                "custom": {"provider": "openai_compatible", "base_url": "", "model": "gpt-4o-mini"},
            }
        if self.merge_form_state is None:
            self.merge_form_state = {}
        if self.download_form_state is None:
            self.download_form_state = {}
        if self.subtitle_form_state is None:
            self.subtitle_form_state = {}


class ConfigStore:
    def __init__(self) -> None:
        self._path = config_path()

    def load(self) -> AppConfig:
        if not self._path.exists():
            cfg = AppConfig()
            self.save(cfg)
            return cfg
        data = json.loads(self._path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(AppConfig)}
        payload = {k: v for k, v in data.items() if k in known}
        return AppConfig(**payload)

    def save(self, cfg: AppConfig) -> None:
        self._path.write_text(
            json.dumps(asdict(cfg), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
