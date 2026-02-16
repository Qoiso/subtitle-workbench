# Subtitle Workbench User Manual (Short)

## 1. Merge

1. In the Merge page, select at least two media categories (video/image, audio, subtitle).
2. Choose output format and output quality.
3. Start merge and monitor progress/logs on the right panel.

Note:
- Lossless merge (`-c copy`) is disabled when image input or hard subtitle is selected.

## 2. Video Download

1. Enter a video URL.
2. Set output directory and cookie mode (optional).
3. Click **Fetch Video Qualities** and choose quality (`Auto Best`, `Video Only`, `Audio Only`).
4. Click **Start Download**.

## 3. Video Localization

Presets:
- One-click Standard Localization
- One-click Audio Localization
- Step-by-step Localization

Local ASR flow:
1. Select `faster-whisper (local)`
2. Download/start model
3. Run task

Cloud ASR flow:
1. Select backend (Gemini/OpenAI/Qwen/custom compatible)
2. Fill API base URL, token, and model name
3. Run **Test ASR Connection**
4. Run task

## 4. Settings

- Configure ffmpeg/ffprobe paths
- Tune blur/overlay
- Run environment check

## 5. Local Data Paths

- Config: `%APPDATA%/ff-merge/config.json`
- Background/preview images: `%APPDATA%/ff-merge/backgrounds/`
- Logs: `%APPDATA%/ff-merge/logs/`
