# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the a650 CLI single-binary build.
# Build:  pyinstaller packaging/a650.spec --distpath dist
# Note: data files are bundled from src/a650/data (package copy), which is the
# path RegisterMap.load() falls back to inside a frozen app (sys._MEIPASS).
from pathlib import Path

ROOT = str(Path(SPECPATH).parent)

a = Analysis(
    [str(Path(ROOT, "entry_a650.py"))],
    pathex=[str(Path(ROOT, "src"))],
    binaries=[],
    datas=[(str(Path(ROOT, "src/a650/data")), "a650/data")],
    hiddenimports=[
        # The whole package must be listed explicitly: with an editable install
        # (__editable__ finder + .pth) PyInstaller's static analysis cannot see
        # src/ and silently drops every a650.* submodule.
        "a650",
        "a650.cli",
        "a650.client",
        "a650.a650lib",
        "a650.a650lib.register_map",
        "a650.a650lib.safety",
        "a650.modbus",
        "a650.modbus.crc",
        "a650.modbus.rtu",
        "a650.transport",
        "a650.transport.base",
        "a650.transport.fake",
        "a650.transport.serial",   # lazy import; harmless if pyserial missing at runtime
        "serial",                  # pyserial (optional at runtime; drop for slim builds)
    ],
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
