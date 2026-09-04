param(
  [string] $InstallerPath = (Join-Path $PSScriptRoot "..\artifacts\installer\Presenter-Copilot-0.1.0-x64-setup.exe")
)

$resolvedInstaller = [System.IO.Path]::GetFullPath($InstallerPath)
$exists = Test-Path -LiteralPath $resolvedInstaller -PathType Leaf

if (-not $exists) {
  [ordered]@{
    status = "unavailable"
    code = "INSTALLER_ARTIFACT_MISSING"
    installer_name = [System.IO.Path]::GetFileName($resolvedInstaller)
    mutates_machine = $false
  } | ConvertTo-Json -Compress
  exit 1
}

[ordered]@{
  status = "manual_required"
  code = "CLEAN_MACHINE_INSTALL_REQUIRED"
  installer_name = [System.IO.Path]::GetFileName($resolvedInstaller)
  mutates_machine = $false
  checklist = @(
    "Use a clean Windows VM or fresh standard-user profile.",
    "Run the unsigned per-user installer and choose an explicit install directory.",
    "Launch without Python, uv, repository paths, or developer environment overrides.",
    "Create a local project and verify the packaged smoke / core handshake.",
    "Import only the checked-in synthetic fixture; verify model preparation is explicit.",
    "Uninstall and verify the application is removed while user data remains.",
    "Reinstall and verify the retained local project opens without a silent download."
  )
} | ConvertTo-Json -Depth 3

# This script is a read-only checklist reporter. It never installs, uninstalls,
# deletes, or changes machine/user application data.
exit 0
