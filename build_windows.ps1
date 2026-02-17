param(
  [string]$Version = "0.4.0",
  [string]$PythonExe = "python",
  [string]$FfmpegBin = "",
  [string]$OutName = "subtitle-workbench"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

if ([string]::IsNullOrWhiteSpace($FfmpegBin)) {
  throw "Please provide -FfmpegBin, for example: -FfmpegBin C:\tools\ffmpeg\bin"
}

$ffmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"
$ffprobeExe = Join-Path $FfmpegBin "ffprobe.exe"
if (!(Test-Path $ffmpegExe)) {
  throw "ffmpeg.exe not found: $ffmpegExe"
}
if (!(Test-Path $ffprobeExe)) {
  throw "ffprobe.exe not found: $ffprobeExe"
}

& $PythonExe -c "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('PyInstaller') else 1)"
if ($LASTEXITCODE -ne 0) {
  & $PythonExe -m pip install pyinstaller
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to install PyInstaller. Check network/proxy or install it manually in the selected Python environment."
  }
}

& $PythonExe -m PyInstaller --noconfirm --clean `
  --name $OutName `
  --windowed `
  --icon "resources/icon/app.ico" `
  --add-data "resources;resources" `
  app/main.py
if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed."
}

$distRoot = Join-Path $repoRoot "dist"
$appRoot = Join-Path $distRoot $OutName
$targetBin = Join-Path $appRoot "resources/ffmpeg/bin"
New-Item -ItemType Directory -Path $targetBin -Force | Out-Null

Copy-Item $ffmpegExe (Join-Path $targetBin "ffmpeg.exe") -Force
Copy-Item $ffprobeExe (Join-Path $targetBin "ffprobe.exe") -Force

$zipName = "Subtitle-Workbench-v$Version-windows-portable.zip"
$zipPath = Join-Path $distRoot $zipName
if (Test-Path $zipPath) {
  Remove-Item $zipPath -Force
}
Compress-Archive -Path (Join-Path $appRoot "*") -DestinationPath $zipPath -CompressionLevel Optimal

$shaPath = Join-Path $distRoot "SHA256SUMS.txt"
$sha256 = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToLower()
"$zipName  $sha256" | Set-Content -Path $shaPath -Encoding UTF8

Write-Host "Portable package ready:"
Write-Host "  $zipPath"
Write-Host "  $shaPath"
