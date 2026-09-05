$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Version = "0.153.4"
$AssetName = "codex-x86_64-pc-windows-msvc.exe"
$ExpectedSha256 = "444a3f0008050605cae73cd9b7a2dcac61294062dfaab56dd20430fd6498518b"
$DownloadUrl = "https://github.com/openai/codex/releases/download/rust-v0.153.4/$AssetName"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$TargetDirectory = Join-Path $RepositoryRoot "artifacts\codex"
$TargetPath = Join-Path $TargetDirectory "codex.exe"
$TemporaryPath = Join-Path $TargetDirectory "codex.exe.download"

function Test-CodexRuntime([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }

    $ActualSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
    if ($ActualSha256 -ne $ExpectedSha256) {
        return $false
    }

    try {
        $VersionOutput = (& $Path --version 2>&1 | Out-String).Trim()
    }
    catch {
        return $false
    }
    return $VersionOutput -eq "codex-cli $Version"
}

New-Item -ItemType Directory -Force -Path $TargetDirectory | Out-Null

if (Test-CodexRuntime $TargetPath) {
    Write-Host "Using verified bundled Codex runtime $Version."
    exit 0
}

Remove-Item -LiteralPath $TargetPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $TemporaryPath -Force -ErrorAction SilentlyContinue

try {
    Write-Host "Fetching official Codex $Version Windows x64 runtime."
    Invoke-WebRequest -UseBasicParsing -Uri $DownloadUrl -OutFile $TemporaryPath

    $DownloadedSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $TemporaryPath).Hash.ToLowerInvariant()
    if ($DownloadedSha256 -ne $ExpectedSha256) {
        throw "Codex runtime SHA-256 mismatch."
    }

    $VersionOutput = (& $TemporaryPath --version 2>&1 | Out-String).Trim()
    if ($VersionOutput -ne "codex-cli $Version") {
        throw "Codex runtime version mismatch: $VersionOutput"
    }

    Move-Item -LiteralPath $TemporaryPath -Destination $TargetPath -Force
    if (-not (Test-CodexRuntime $TargetPath)) {
        throw "Codex runtime failed post-install verification."
    }
}
catch {
    Remove-Item -LiteralPath $TemporaryPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $TargetPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host "Prepared verified bundled Codex runtime $Version at $TargetPath."
