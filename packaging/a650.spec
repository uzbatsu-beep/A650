# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
ROOT = str(Path(SPECPATH).parent)
# PyInstaller spec for the a650 CLI single-binary build.
# Build:  pyinstaller packaging/a650.spec --distpath dist
# Note: data files are bundled from src/a650/data (package copy), which is the
# path RegisterMap.load() falls back to inside a frozen app (sys._MEIPASS).

a = Analysis(
    [str(Path(ROOT, "scripts/a650.py"))],
    pathex=[str(Path(ROOT, "src"))],
    binaries=[],
    datas=[(str(Path(ROOT, "src/a650/data")), "a650/data")],
    hiddenimports=["serial"],  # pyserial is optional at runtime; drop for slim builds
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="a650",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
