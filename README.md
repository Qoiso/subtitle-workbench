# Subtitle Workbench

`Subtitle Workbench` is a Windows-first desktop toolkit for:

- media merge (video/image/audio/subtitle)
- video download (`yt-dlp`)
- subtitle localization (ASR -> translate -> mux)

The app UI supports Chinese / Japanese / English.

## Core Features

1. **素材合并 / Merge**
   - Supports image/video + audio + subtitle combinations
   - Output quality options: `CPU-H.264`, `NVIDIA-GPU-H.265`, `Lossless Merge (-c copy)` (when applicable)
2. **视频下载 / Video Download**
   - URL download via `yt-dlp`
   - Format selection (`Auto Best`, `Video Only`, `Audio Only`)
   - Cookie modes: browser / file / none
3. **视频字幕化 / Video Localization**
   - Local ASR: `faster-whisper`
   - Cloud ASR: OpenAI-compatible endpoints (Gemini/OpenAI/Qwen/custom route)
   - Translation providers: OpenAI-compatible endpoints
   - One-click and step-by-step workflows

## Terminology

- Community term `烤肉` is treated as a legacy alias.
- Product/UI wording uses professional terms:
  - Chinese: `汉化` / `字幕化`
  - Japanese: `字幕化`
  - English: `Localization`

## Quick Start (Source Mode)

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Put `ffmpeg.exe` and `ffprobe.exe` under:

```text
resources/ffmpeg/bin/
```

3. Run:

```bash
python -m app.main
```

## Windows Portable Build

Use the build script (FFmpeg binaries are injected from an external path):

```powershell
.\build_windows.ps1 -Version 0.4.0 -FfmpegBin "C:\tools\ffmpeg\bin"
```

Output:

- `dist/Subtitle-Workbench-v0.4.0-windows-portable.zip`
- `dist/SHA256SUMS.txt`

## Privacy Notes

- User settings and custom images are stored in:
  - `%APPDATA%/ff-merge/config.json`
  - `%APPDATA%/ff-merge/backgrounds/*`
- These files are **not** part of the repository.
- Before publishing, run:

```powershell
.\scripts\privacy_check.ps1
```

## Release Checklist

See `docs/release-checklist.md`.

## Legal

- License: `MIT` (`LICENSE`)
- Third-party notices: `THIRD_PARTY_NOTICES.md`
- Legal disclaimer: `LEGAL_DISCLAIMER.md`

