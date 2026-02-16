# Changelog

All notable changes are documented in this file.

## 0.4.0

### Added
- Privacy guardrails (`scripts/privacy_check.ps1`, extended `.gitignore`)
- Portable release packaging with SHA256 output (`build_windows.ps1`)
- Publication docs (`LEGAL_DISCLAIMER.md`, `THIRD_PARTY_NOTICES.md`, user manuals, release checklist)

### Changed
- Product naming updated to `Subtitle Workbench`
- UI terminology normalized from community slang (`烤肉` / `roast`) to `Localization` wording
- App version aligned to `0.4.0`

### Notes
- FFmpeg binaries are no longer intended for source repository tracking.
- Existing local config path remains `%APPDATA%/ff-merge` for compatibility.
