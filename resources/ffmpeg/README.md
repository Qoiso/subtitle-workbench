# FFmpeg Binary Placement

This repository does not track `ffmpeg.exe` / `ffprobe.exe` binaries.

For local source-mode run, place them manually under:

```text
resources/ffmpeg/bin/ffmpeg.exe
resources/ffmpeg/bin/ffprobe.exe
```

For release builds, use:

```powershell
.\build_windows.ps1 -Version X.Y.Z -FfmpegBin "C:\path\to\ffmpeg\bin"
```

The build script copies binaries into the portable package output.
