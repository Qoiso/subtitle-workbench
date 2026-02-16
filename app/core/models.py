from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal


class MediaKind(str, Enum):
    VISUAL = "visual"
    AUDIO = "audio"
    SUBTITLE = "subtitle"


class TaskType(str, Enum):
    MERGE = "merge"
    DOWNLOAD = "download"
    SUBTITLE = "subtitle"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


CookiesMode = Literal["browser", "file", "none"]


@dataclass(slots=True)
class MergeInput:
    visual_paths: list[str]
    audio_paths: list[str]
    subtitle_paths: list[str]
    output_path: str
    image_paths: list[str] = field(default_factory=list)
    output_quality: Literal["cpu_h264", "nvidia_h265", "lossless_copy"] = "cpu_h264"
    subtitle_mode: Literal["soft", "hard"] = "soft"
    output_container: str = "mkv"
    sync_mode: Literal["longest", "shortest", "video", "audio"] = "longest"


@dataclass(slots=True)
class DownloadInput:
    url: str
    output_dir: str
    format_selector: str | None = None
    cookies_mode: CookiesMode = "none"
    cookies_file: str | None = None
    browser_name: str | None = None


TranslatorProvider = Literal[
    "none",
    "ollama",
    "lmstudio",
    "openai",
    "qwen",
    "deepseek",
    "gemini_official",
    "openrouter",
    "openai_compatible",
]


@dataclass(slots=True)
class SubtitleJobInput:
    video_path: str
    output_dir: str
    preset_mode: Literal["one_click_normal", "one_click_voice", "step_by_step"] = "step_by_step"
    voice_image_path: str | None = None
    voice_audio_path: str | None = None
    voice_subtitle_path: str | None = None
    voice_output_container: Literal["mkv", "mp4"] = "mkv"
    voice_output_quality: Literal["cpu_h264", "nvidia_h265", "lossless_copy"] = "cpu_h264"
    voice_subtitle_mode: Literal["soft", "hard"] = "soft"
    asr_backend: Literal[
        "faster_whisper",
        "asr_gemini",
        "asr_openai",
        "asr_qwen",
        "asr_openai_compatible",
    ] = "faster_whisper"
    whisper_model: Literal["small", "medium", "large-v3", "large-v3-turbo"] = "large-v3"
    asr_compute_type: Literal["auto", "float16", "int8"] = "auto"
    model_dir: str | None = None
    asr_api_base_url: str | None = None
    asr_api_key: str | None = None
    asr_model_name: str = "gpt-4o-mini-transcribe"
    source_lang: str = "auto"
    target_lang: str = "zh"
    translator_provider: TranslatorProvider = "none"
    api_base_url: str | None = None
    api_key: str | None = None
    model_name: str = "gpt-4o-mini"
    extra_headers: dict[str, str] | None = None
    auto_unload_after_asr: bool = False
    run_mode: Literal["all", "asr_only", "translate_only", "embed_only"] = "all"


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    code: str
    message: str


@dataclass(slots=True)
class MediaMeta:
    path: str
    has_video: bool
    has_audio: bool
    has_subtitle: bool
    duration: float | None = None
    format_name: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None


@dataclass(slots=True)
class FormatInfo:
    format_id: str
    ext: str
    note: str
    resolution: str | None = None
    vcodec: str | None = None
    acodec: str | None = None


@dataclass(slots=True)
class DownloadResult:
    filepath: str | None
    title: str | None


ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    task_type: TaskType
    status: TaskStatus
    payload: MergeInput | DownloadInput | SubtitleJobInput
    message: str = ""
    progress: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)
