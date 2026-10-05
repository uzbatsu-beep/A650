"""PyInstaller entry point for the a650 CLI (single-file build).

File name must not be "a650.py": PyInstaller would register this __main__
script under module name "a650", shadowing the real a650 package in the PYZ
archive and breaking `from a650.cli import main` at runtime.
"""
from a650.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
