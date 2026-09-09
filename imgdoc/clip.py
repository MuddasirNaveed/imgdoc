"""Clipboard hotkey: turn a copied image into Markdown, in place.

Copy an image, press your hotkey, paste. The clipboard now holds Markdown
instead of a picture, so it works in any app — browser chat, Slack, an editor.

Run with:  python3 -m imgdoc.clip
"""
import os
import shutil
import subprocess
import sys

from . import intake, render
from .config import DEFAULT
from .pipeline import process_loaded

IMAGE_TYPES = ("image/png", "image/jpeg", "image/bmp", "image/tiff", "image/webp")


class ClipboardError(Exception):
    pass


def _wayland() -> bool:
    """Wayland and X11 need different tools. Trust the session variable, then
    fall back to which binary is actually installed."""
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return True
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return shutil.which("wl-paste") is not None and shutil.which("xclip") is None


def _run(cmd: list[str], stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise ClipboardError(f"{cmd[0]}: {proc.stderr.decode().strip()}")
    return proc.stdout


def read_image() -> tuple[bytes, str]:
    """Return (raw_bytes, mime) for an image on the clipboard."""
    if _wayland():
        _require("wl-paste", "wl-clipboard")
        offered = _run(["wl-paste", "--list-types"]).decode().split()
        mime = next((t for t in IMAGE_TYPES if t in offered), None)
        if mime is None:
            raise ClipboardError("clipboard holds no image "
                                 f"(offers: {', '.join(offered) or 'nothing'})")
        return _run(["wl-paste", "--no-newline", "--type", mime]), mime

    _require("xclip", "xclip")
    targets = _run(["xclip", "-selection", "clipboard",
                    "-t", "TARGETS", "-o"]).decode().split()
    mime = next((t for t in IMAGE_TYPES if t in targets), None)
    if mime is None:
        raise ClipboardError("clipboard holds no image "
                             f"(offers: {', '.join(targets) or 'nothing'})")
    return _run(["xclip", "-selection", "clipboard", "-t", mime, "-o"]), mime


def write_text(text: str) -> None:
    if _wayland():
        _require("wl-copy", "wl-clipboard")
        _run(["wl-copy", "--type", "text/plain"], stdin=text.encode())
    else:
        _require("xclip", "xclip")
        subprocess.run(["xclip", "-selection", "clipboard", "-t", "text/plain"],
                       input=text.encode(), check=True)


def _require(binary: str, package: str) -> None:
    if shutil.which(binary) is None:
        raise ClipboardError(f"{binary} not found — install it with "
                             f"'sudo apt install {package}'")


def notify(title: str, body: str, urgency: str = "normal") -> None:
    """Desktop notification. Without feedback you would be pasting blind."""
    if shutil.which("notify-send") is None:
        print(f"{title}: {body}", file=sys.stderr)
        return
    subprocess.run(["notify-send", "-u", urgency, "-a", "imgdoc", title, body],
                   stderr=subprocess.DEVNULL)


def main() -> int:
    try:
        raw, mime = read_image()
    except ClipboardError as exc:
        notify("imgdoc", str(exc), "critical")
        print(exc, file=sys.stderr)
        return 2

    try:
        bgr, meta = intake.load_bytes(raw, f"clipboard ({mime})")
        doc = process_loaded(bgr, meta, DEFAULT, stem="clipboard")
    except Exception as exc:
        notify("imgdoc failed", f"{type(exc).__name__}: {exc}", "critical")
        print(exc, file=sys.stderr)
        return 1

    q = doc["quality"]
    summary = (f"confidence {q['mean_ocr_confidence']} · "
               f"{q['word_count']} words · {len(doc['blocks'])} blocks")

    # A reject means the text is probably wrong. Replacing a good image with
    # bad text is the worst outcome, so leave the clipboard alone and say why.
    if q["verdict"] == "reject":
        notify("imgdoc: rejected — image kept on clipboard",
               "\n".join([summary] + q["reasons"][:3]), "critical")
        print("rejected:", "; ".join(q["reasons"]), file=sys.stderr)
        return 1

    write_text(render.to_markdown(doc))
    urgency = "normal" if q["verdict"] == "pass" else "normal"
    title = ("imgdoc: Markdown copied" if q["verdict"] == "pass"
             else "imgdoc: copied — check it")
    notify(title, "\n".join([summary] + q["reasons"][:2]), urgency)
    print(f"{q['verdict']}: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
