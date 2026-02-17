# Subtitle Workbench v0.4.0

## Highlights

- Rebranded product naming and UI terminology for clearer global usage
- Privacy-first publishing workflow (no personal config/images tracked)
- GitHub-ready clean history without bundled FFmpeg binaries in source
- Stable Windows portable packaging pipeline with SHA256 checksum output

## New in this release

- Product display name updated to **Subtitle Workbench**
- i18n title updates:
  - zh: 字幕工作台
  - ja: 字幕ワークベンチ
  - en: Subtitle Workbench
- Community slang (`烤肉` / `roast`) replaced in UI/runtime text by professional localization wording
- Added publishing/legal docs:
  - `LICENSE` (MIT)
  - `CHANGELOG.md`
  - `THIRD_PARTY_NOTICES.md`
  - `LEGAL_DISCLAIMER.md`
  - `CONTRIBUTING.md`
- Added user docs:
  - `docs/user-manual.zh-CN.md`
  - `docs/user-manual.ja.md`
  - `docs/user-manual.en.md`
  - `docs/release-checklist.md`
- Added privacy guard script:
  - `scripts/privacy_check.ps1`
- Build pipeline improvements:
  - `build_windows.ps1` now supports external FFmpeg injection
  - Generates portable zip + `SHA256SUMS.txt`
  - Fails fast when PyInstaller install/build fails

## Important repo policy change

- FFmpeg binaries are **not tracked** in source repository anymore.
- For source-mode run, place binaries locally under:
  - `resources/ffmpeg/bin/ffmpeg.exe`
  - `resources/ffmpeg/bin/ffprobe.exe`
- For release build, use external FFmpeg path via build script parameter.

## Assets

- `Subtitle-Workbench-v0.4.0-windows-portable.zip`
- `SHA256SUMS.txt`

## Notes

- Windows-first release (portable only)
- Local app data path remains `%APPDATA%/ff-merge` for backward compatibility

