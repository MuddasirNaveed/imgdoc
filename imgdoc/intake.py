"""Stage 0: intake. Load bytes, identify the real format, fix EXIF orientation."""
import hashlib
import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


class IntakeError(Exception):
    pass


def load(path: Path):
    """Return (bgr_array, meta) for a file on disk."""
    return load_bytes(path.read_bytes(), str(path))


def load_bytes(raw: bytes, label: str):
    """Return (bgr_array, meta) for raw image bytes.

    Used by the clipboard path, where the image never touches disk.
    Format still comes from the bytes, never from a filename.
    """
    if not raw:
        raise IntakeError(f"{label} is empty")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        raise IntakeError(f"{label} is not a readable image: {exc}") from exc

    fmt = img.format  # from the decoded header, not the filename
    before = img.size

    # Phone photos carry an orientation flag most libraries ignore. Skipping
    # this alone produces sideways output, so it happens before anything else.
    img = ImageOps.exif_transpose(img)
    transposed = img.size != before

    if img.mode != "RGB":
        img = img.convert("RGB")

    meta = {
        "path": label,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "format": fmt,
        "width": img.width,
        "height": img.height,
        "exif_transposed": transposed,
    }
    bgr = np.array(img)[:, :, ::-1].copy()  # PIL RGB -> OpenCV BGR
    return bgr, meta
