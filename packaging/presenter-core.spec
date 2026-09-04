"""Reproducible PyInstaller one-folder build for the Windows core sidecar."""

from pathlib import Path

from PyInstaller.building.build_main import Analysis, COLLECT, EXE, PYZ
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).resolve().parent
CORE = ROOT / "core"
ENTRYPOINT = CORE / "presenter_core" / "__main__.py"

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = [
    "ctranslate2",
    "faster_whisper",
    "fastembed",
    "sounddevice",
    "win32cred",
]

# These packages use importlib/plugin metadata at runtime.  Collect their
# Python support files and native libraries, but never collect their model
# caches; models remain an explicit, per-user setup concern.
for package in ("fastembed", "faster_whisper"):
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except ImportError:
        continue
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hidden)

analysis = Analysis(
    [str(ENTRYPOINT)],
    pathex=[str(CORE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="presenter-core",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    analysis.zipfiles,
    analysis.zipped_data,
    strip=False,
    upx=False,
    name="presenter-core",
)
