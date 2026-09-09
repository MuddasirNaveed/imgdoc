# PyInstaller spec — builds on both Linux and Windows from the same file.
import os
import sys
from pathlib import Path

block_cipher = None
IS_WIN = sys.platform.startswith("win")

# Windows must ship Tesseract inside the exe: there is no package manager to
# depend on. Linux does not, because the .deb declares Depends: tesseract-ocr.
# Populate vendor/tesseract/ before building on Windows (see build_windows.md).
datas = []
vendor = Path("vendor/tesseract")
if IS_WIN and vendor.is_dir():
    datas.append((str(vendor), "tesseract"))

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    runtime_hooks=[],
    # Trim heavy transitive deps PyInstaller pulls in but this app never uses.
    excludes=["matplotlib", "scipy", "pandas", "pytest", "IPython", "notebook"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="imgdoc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # No console window on Windows: this is a desktop app. On Linux the
    # binary is also used from a terminal, so keep stdout there.
    console=not IS_WIN,
)
