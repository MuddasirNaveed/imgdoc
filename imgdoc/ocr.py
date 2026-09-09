"""Stage 5: OCR with geometry retained.

Page segmentation (columns, blocks, reading order) is delegated to
Tesseract rather than reimplemented — it already groups words into
block/paragraph/line and orders them. We keep every box and every
confidence value, because both are what the validation stage runs on.
"""
import numpy as np
import pytesseract
from pytesseract import Output

from .config import Config


def _conf(value) -> float:
    """conf comes back as int in some versions, str in others."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def words(gray: np.ndarray, cfg: Config) -> list[dict]:
    data = pytesseract.image_to_data(
        gray,
        lang=cfg.tesseract_lang,
        config=f"--psm {cfg.tesseract_psm}",
        output_type=Output.DICT,
    )

    out = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        conf = _conf(data["conf"][i])
        if not text or conf < 0:
            continue
        out.append({
            "text": text,
            "conf": conf,
            "left": int(data["left"][i]),
            "top": int(data["top"][i]),
            "width": int(data["width"][i]),
            "height": int(data["height"][i]),
            "block": int(data["block_num"][i]),
            "par": int(data["par_num"][i]),
            "line": int(data["line_num"][i]),
        })
    return out


def group_lines(word_list: list[dict]) -> list[dict]:
    """Fold words into lines using Tesseract's own block/par/line indices."""
    buckets: dict[tuple, list[dict]] = {}
    for w in word_list:
        buckets.setdefault((w["block"], w["par"], w["line"]), []).append(w)

    lines = []
    for key, ws in buckets.items():
        ws.sort(key=lambda w: w["left"])
        x0 = min(w["left"] for w in ws)
        y0 = min(w["top"] for w in ws)
        x1 = max(w["left"] + w["width"] for w in ws)
        y1 = max(w["top"] + w["height"] for w in ws)
        lines.append({
            "text": " ".join(w["text"] for w in ws),
            "bbox": (x0, y0, x1, y1),
            "height": float(np.median([w["height"] for w in ws])),
            "conf": float(np.mean([w["conf"] for w in ws])),
            "min_conf": float(min(w["conf"] for w in ws)),
            "block": key[0],
            "par": key[1],
            "line": key[2],
        })

    lines.sort(key=lambda l: (l["block"], l["par"], l["line"]))
    return lines
