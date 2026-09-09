"""Orchestration. Stage order matches the documented pipeline exactly."""
from pathlib import Path

import cv2
import numpy as np

from . import intake, ocr, preprocess, quality, structure, tables
from .config import Config


def process(path: Path, cfg: Config, use_dewarp: bool = False,
            strict: bool = False, debug_dir: Path | None = None) -> dict:
    bgr, meta = intake.load(path)
    return process_loaded(bgr, meta, cfg, use_dewarp, strict, debug_dir, path.stem)


def process_loaded(bgr, meta: dict, cfg: Config, use_dewarp: bool = False,
                   strict: bool = False, debug_dir: Path | None = None,
                   stem: str = "image") -> dict:

    # Everything downstream assumes dark ink on light paper. Normalise a
    # dark-mode screenshot before it is measured, not after.
    inverted = quality.is_light_on_dark(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    if inverted:
        bgr = cv2.bitwise_not(bgr)
    meta["polarity_inverted"] = inverted

    q = quality.assess(bgr, cfg)
    if strict and not q["input_ok"]:
        return _rejected(meta, q)

    gray, steps = preprocess.run(bgr, cfg, q["median_text_height_px"], use_dewarp)

    found = tables.find_tables(gray, cfg)
    table_boxes = [t["bbox"] for t in found]

    word_list = ocr.words(gray, cfg)
    lines = ocr.group_lines(word_list)
    blocks = structure.classify(lines, cfg, table_boxes)

    for table in found:
        ok, problems = tables.integrity(table, cfg)
        blocks.append({
            "type": "table",
            "rows": table["rows"],
            "shape": table["shape"],
            "bbox": list(table["bbox"]),
            "confidence": None,
            "min_word_confidence": 100 if ok else 0,
            "problems": problems,
        })

    blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
    for i, block in enumerate(blocks):
        block["id"] = f"b{i:03d}"
        block["order"] = i
        block["bbox_norm"] = _normalise(block["bbox"], gray.shape)

    mean_conf = (
        round(float(np.mean([w["conf"] for w in word_list])), 1) if word_list else 0.0
    )
    verdict, reasons = _verdict(q, mean_conf, blocks, len(word_list), cfg)

    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / f"{stem}.processed.png"), gray)

    return {
        "schema_version": "1.0",
        "source": meta,
        "preprocessing": steps,
        "quality": {
            **{k: v for k, v in q.items() if k not in ("input_reasons", "input_ok")},
            "mean_ocr_confidence": mean_conf,
            "word_count": len(word_list),
            "verdict": verdict,
            "reasons": reasons,
        },
        "processed_size": {"width": gray.shape[1], "height": gray.shape[0]},
        "blocks": blocks,
        "_low_conf_threshold": cfg.word_conf_min,
    }


def _normalise(bbox, shape) -> list[float]:
    """Boxes are normalised against the PROCESSED image, not the original.
    Save the processed image (--debug-dir) if you need to verify them."""
    h, w = shape[:2]
    return [round(bbox[0] / w, 4), round(bbox[1] / h, 4),
            round(bbox[2] / w, 4), round(bbox[3] / h, 4)]


def _verdict(q: dict, mean_conf: float, blocks: list, word_count: int,
             cfg: Config) -> tuple:
    reasons = list(q["input_reasons"])
    if mean_conf < cfg.conf_review:
        reasons.append(f"mean OCR confidence {mean_conf} below {cfg.conf_review}")
    elif mean_conf < cfg.conf_pass:
        reasons.append(f"mean OCR confidence {mean_conf} below pass bar {cfg.conf_pass}")
    for block in blocks:
        if block["type"] == "table" and block.get("problems"):
            reasons.append(f"table {block.get('shape')}: {'; '.join(block['problems'])}")
    if not blocks:
        reasons.append("no text blocks produced")
    if 0 < word_count < cfg.min_words:
        reasons.append(
            f"only {word_count} words extracted; too little text for the "
            "confidence figure to mean anything"
        )

    if not reasons:
        return "pass", []
    # The input checks are pre-OCR proxies for "OCR will fail". When OCR then
    # comes back strong, the proxy was wrong: screen-rendered text is legible
    # at glyph heights that would be unrecoverable in a photograph. Demote to
    # review rather than reject, and say why.
    # A high mean confidence over a handful of words is the average of a few
    # lucky reads, not evidence the page was recognised. Require enough text
    # before letting OCR results override the pre-OCR checks.
    if mean_conf >= cfg.conf_pass and blocks and word_count >= cfg.min_words:
        if not q["input_ok"]:
            reasons.append(
                f"input checks failed but OCR confidence is {mean_conf}; "
                "pre-OCR heuristics overridden"
            )
        return "review", reasons
    if mean_conf < cfg.conf_review or not blocks or not q["input_ok"]:
        return "reject", reasons
    return "review", reasons


def _rejected(meta: dict, q: dict) -> dict:
    return {
        "schema_version": "1.0",
        "source": meta,
        "preprocessing": {},
        "quality": {**{k: v for k, v in q.items()
                       if k not in ("input_reasons", "input_ok")},
                    "mean_ocr_confidence": None,
                    "word_count": 0,
                    "verdict": "reject",
                    "reasons": q["input_reasons"]},
        "processed_size": None,
        "blocks": [],
        "_low_conf_threshold": 0,
    }
