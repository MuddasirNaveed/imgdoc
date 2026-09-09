"""Stage 6: structure inference.

Every rule here is RELATIVE, never an absolute pixel threshold. DPI is
unknown for an image, so a heading is defined as 'taller than the median
line on this page', not 'taller than 24px'.
"""
import re

import numpy as np

from .config import Config

KV_PATTERN = re.compile(r"^\s*([^:]{1,60}?)\s*[:\uFF1A]\s*(.+?)\s*$")


def classify(lines: list[dict], cfg: Config, table_boxes: list[tuple]) -> list[dict]:
    """Turn OCR lines into typed blocks. Lines inside a table region are
    dropped here — the table extractor already read them cell by cell."""
    kept = [l for l in lines if not _inside_any(l["bbox"], table_boxes)]
    if not kept:
        return []

    median_height = float(np.median([l["height"] for l in kept]))
    blocks = []

    for line in kept:
        ratio = line["height"] / median_height if median_height else 1.0
        block = {
            "text": line["text"],
            "bbox": list(line["bbox"]),
            "confidence": round(line["conf"], 1),
            "min_word_confidence": round(line["min_conf"], 1),
            "height_ratio": round(ratio, 2),
        }

        kv = _key_value(line["text"], cfg)
        if ratio >= cfg.heading_ratio_h1:
            block.update(type="heading", level=1)
        elif ratio >= cfg.heading_ratio:
            block.update(type="heading", level=2)
        elif kv:
            block.update(type="key_value", key=kv[0], value=kv[1])
        else:
            block["type"] = "text"

        blocks.append(block)

    return _merge_paragraphs(blocks, median_height)


def _key_value(text: str, cfg: Config) -> tuple[str, str] | None:
    match = KV_PATTERN.match(text)
    if not match:
        return None
    key, value = match.group(1), match.group(2)
    if not value or len(key.split()) > cfg.kv_max_key_words:
        return None
    return key, value


def _merge_paragraphs(blocks: list[dict], median_height: float) -> list[dict]:
    """Join consecutive plain-text lines whose vertical gap is small
    relative to the line height. Headings and key-values stay separate."""
    merged: list[dict] = []
    for block in blocks:
        prev = merged[-1] if merged else None
        joinable = (
            prev is not None
            and prev["type"] == "text"
            and block["type"] == "text"
            and (block["bbox"][1] - prev["bbox"][3]) < median_height * 0.8
        )
        if joinable:
            prev["text"] += " " + block["text"]
            prev["bbox"] = [
                min(prev["bbox"][0], block["bbox"][0]),
                min(prev["bbox"][1], block["bbox"][1]),
                max(prev["bbox"][2], block["bbox"][2]),
                max(prev["bbox"][3], block["bbox"][3]),
            ]
            prev["confidence"] = round(
                (prev["confidence"] + block["confidence"]) / 2, 1
            )
            prev["min_word_confidence"] = min(
                prev["min_word_confidence"], block["min_word_confidence"]
            )
        else:
            merged.append(dict(block))
    return merged


def _inside_any(bbox, boxes: list[tuple]) -> bool:
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    return any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in boxes)
