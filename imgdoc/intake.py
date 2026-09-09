"""Stage 0: intake. Load bytes, identify the real format, fix EXIF orientation."""
import hashlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


class IntakeError(Exception):
    pass


def load(path: Path):
    """Return (bgr_array, meta). Format comes from the bytes, not the extension."""
    raw = path.read_bytes()
    if not raw:
        raise IntakeError(f"{path} is empty")

    try:
        img = Image.open(path)
        img.load()
    except Exception as exc:
        raise IntakeError(f"{path} is not a readable image: {exc}") from exc

    fmt = img.format  # from the decoded header, not the filename
    before = img.size

    # Phone photos carry an orientation flag most libraries ignore. Skipping
    # this alone produces sideways output, so it happens before anything else.
    img = ImageOps.exif_transpose(img)
    transposed = img.size != before

    if img.mode != "RGB":
        img = img.convert("RGB")

    meta = {
        "path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "format": fmt,
        "width": img.width,
        "height": img.height,
        "exif_transposed": transposed,
    }
    bgr = np.array(img)[:, :, ::-1].copy()  # PIL RGB -> OpenCV BGR
    return bgr, meta
