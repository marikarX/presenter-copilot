$ErrorActionPreference = 'Stop'
$probeRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('presenter-codex-gate-' + [guid]::NewGuid())
New-Item -ItemType Directory -Path $probeRoot | Out-Null
$previousExecutable = $env:PRESENTER_CODEX_EXECUTABLE
try {
    foreach ($version in @('0.153.1', '0.153.4')) {
        $installRoot = Join-Path $probeRoot $version
        & npm install --prefix $installRoot --ignore-scripts --no-audit --no-fund "@openai/codex@$version"
        if ($LASTEXITCODE -ne 0) { throw 'Pinned Codex installation failed.' }
        $env:PRESENTER_CODEX_EXECUTABLE = Join-Path $installRoot 'node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
        & uv run --directory core --project . --locked python -m presenter_core.tools.codex_acceptance --probe
        if ($LASTEXITCODE -ne 0) { throw "Codex containment failed for $version." }
    }
} finally {
    $env:PRESENTER_CODEX_EXECUTABLE = $previousExecutable
    # Only delete the exact disposable directory allocated above, never an input path.
    $resolvedProbe = [System.IO.Path]::GetFullPath($probeRoot)
    $resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    if (-not $resolvedProbe.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing cleanup outside the temporary root.'
    }
    if (Test-Path -LiteralPath $resolvedProbe) { Remove-Item -LiteralPath $resolvedProbe -Recurse -Force }
}
