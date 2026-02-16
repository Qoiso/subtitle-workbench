from __future__ import annotations

from pathlib import Path


APP_NAME = "ff-merge"


def app_data_dir() -> Path:
    base = Path.home() / "AppData" / "Roaming"
    path = base / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backgrounds_dir() -> Path:
    path = app_data_dir() / "backgrounds"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_dir() / "config.json"


def cookies_dir() -> Path:
    path = app_data_dir() / "cookies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def bundled_ffmpeg_path() -> Path:
    return project_root() / "resources" / "ffmpeg" / "bin" / "ffmpeg.exe"


def bundled_ffprobe_path() -> Path:
    return project_root() / "resources" / "ffmpeg" / "bin" / "ffprobe.exe"
