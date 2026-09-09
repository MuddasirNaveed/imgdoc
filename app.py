"""Entry point for the packaged application.

No arguments launches the GUI, which is what a double-clicked icon does.
Any arguments fall through to the CLI, so the same binary works from a
terminal.
"""
import multiprocessing
import os
import sys
from pathlib import Path


def _bundled_tesseract() -> None:
    """Point pytesseract at the bundled binary when frozen.

    PyInstaller unpacks data files to sys._MEIPASS. On Windows the Tesseract
    binary and its tessdata ship inside the exe; on Linux the .deb declares a
    dependency on tesseract-ocr instead, so there is nothing to wire up.
    """
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return
    root = Path(base) / "tesseract"
    if not root.is_dir():
        return

    binary = root / ("tesseract.exe" if os.name == "nt" else "tesseract")
    if binary.exists():
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = str(binary)
    tessdata = root / "tessdata"
    if tessdata.is_dir():
        os.environ["TESSDATA_PREFIX"] = str(tessdata)


def main() -> int:
    multiprocessing.freeze_support()  # required on Windows for frozen apps
    _bundled_tesseract()

    if len(sys.argv) > 1 and sys.argv[1] == "--clip":
        from imgdoc.clip import main as clip_main
        return clip_main()

    if len(sys.argv) > 1:
        from imgdoc.cli import main as cli_main
        return cli_main()

    from imgdoc.gui import main as gui_main
    gui_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
