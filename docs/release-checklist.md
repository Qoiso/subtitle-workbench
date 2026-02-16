# Release Checklist (Windows Portable)

## 1. Privacy

- [ ] Run `.\scripts\privacy_check.ps1`
- [ ] Confirm `git status --short` has no personal image/config files
- [ ] Confirm `%APPDATA%/ff-merge` content is not part of repo

## 2. Version and Docs

- [ ] `app/version.py` matches release tag
- [ ] `CHANGELOG.md` updated
- [ ] `README.md` reviewed
- [ ] Legal files present (`LICENSE`, `THIRD_PARTY_NOTICES.md`, `LEGAL_DISCLAIMER.md`)

## 3. Build

- [ ] Build portable package:
  - `.\build_windows.ps1 -Version X.Y.Z -FfmpegBin "C:\path\to\ffmpeg\bin"`
- [ ] Verify `dist/Subtitle-Workbench-vX.Y.Z-windows-portable.zip`
- [ ] Verify `dist/SHA256SUMS.txt`

## 4. Smoke Test

- [ ] Launch app from portable output
- [ ] Merge page basic workflow works
- [ ] Video download page basic workflow works
- [ ] Video localization page basic workflow works
- [ ] i18n switching (zh/ja/en) works

## 5. Git and Tag

- [ ] Commit release changes
- [ ] Create tag `vX.Y.Z`
- [ ] Push branch and tag

