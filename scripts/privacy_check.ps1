$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location $repoRoot

$violations = New-Object System.Collections.Generic.List[string]

function Add-Violation([string]$path) {
    if (-not [string]::IsNullOrWhiteSpace($path)) {
        $violations.Add($path)
    }
}

# 1) Check tracked files for sensitive naming patterns.
$tracked = @()
try {
    $tracked = git ls-files
} catch {
    Write-Error "Failed to list tracked files. Ensure this script runs inside a git repository."
    exit 2
}

$namePattern = '(user_bg|preview_1|preview_2)'
$snapshotPattern = '(^|[\\/])(config|settings)\.json$'

foreach ($path in $tracked) {
    if ($path -match $namePattern -or $path -match $snapshotPattern) {
        Add-Violation "tracked: $path"
    }
}

# 2) Check staged files too.
$staged = @()
try {
    $staged = git diff --cached --name-only
} catch {
    $staged = @()
}
foreach ($path in $staged) {
    if ($path -match $namePattern -or $path -match $snapshotPattern) {
        Add-Violation "staged:  $path"
    }
}

# 3) Check repository working tree for suspicious config snapshots in project folders.
$localSnapshots = Get-ChildItem -Recurse -File -Force -Include config.json,settings.json |
    Where-Object {
        $_.FullName -notmatch '\\\.git\\' -and
        $_.FullName -notmatch '\\dist\\' -and
        $_.FullName -notmatch '\\build\\' -and
        $_.FullName -notmatch '\\__pycache__\\'
    }

foreach ($file in $localSnapshots) {
    $relative = Resolve-Path -Relative $file.FullName
    if ($relative -notmatch '^\.\.(\\|/)' -and $relative -notmatch '^\.\\?venv') {
        Add-Violation "snapshot: $relative"
    }
}

if ($violations.Count -gt 0) {
    Write-Host "Privacy check failed. Potentially sensitive files detected:" -ForegroundColor Red
    $violations | Sort-Object -Unique | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "Privacy check passed." -ForegroundColor Green
exit 0
