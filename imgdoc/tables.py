"""Ruled-table extraction.

Tables are pulled out BEFORE page OCR and read cell by cell, because a
table read as flowing prose produces plausible-looking wrong numbers.

Scope: ruled tables only (visible horizontal and vertical lines).
Borderless tables are NOT handled here and will fall through to the prose
extractor. That is a deliberate limitation, not an oversight.
"""
import cv2
import numpy as np
import pytesseract

from .config import Config


def _line_mask(binary: np.ndarray, horizontal: bool, min_len: int) -> np.ndarray:
    size = (min_len, 1) if horizontal else (1, min_len)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, size)
    mask = cv2.erode(binary, kernel, iterations=1)
    return cv2.dilate(mask, kernel, iterations=1)


def _cluster(values: list[int], tolerance: int = 8) -> list[int]:
    """Collapse near-duplicate line positions into single coordinates."""
    if not values:
        return []
    values = sorted(values)
    groups, current = [], [values[0]]
    for v in values[1:]:
        if v - current[-1] <= tolerance:
            current.append(v)
        else:
            groups.append(int(np.mean(current)))
            current = [v]
    groups.append(int(np.mean(current)))
    return groups


def find_tables(gray: np.ndarray, cfg: Config) -> list[dict]:
    """Return a list of {'bbox': (x0,y0,x1,y1), 'rows': [[cell,...],...]}."""
    h, w = gray.shape
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10
    )

    h_mask = _line_mask(binary, True, max(30, int(w * 0.15)))
    v_mask = _line_mask(binary, False, max(30, int(h * 0.05)))
    grid = cv2.dilate(cv2.bitwise_or(h_mask, v_mask),
                      np.ones((3, 3), np.uint8), iterations=2)

    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    tables = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < w * 0.2 or ch < 40:
            continue

        region_h = h_mask[y:y + ch, x:x + cw]
        region_v = v_mask[y:y + ch, x:x + cw]

        # A row line must span most of the region's width, and likewise columns.
        rows = _cluster([int(i) for i in range(ch)
                         if region_h[i].sum() / 255 > cw * cfg.table_line_ratio])
        cols = _cluster([int(j) for j in range(cw)
                         if region_v[:, j].sum() / 255 > ch * cfg.table_line_ratio])

        if len(rows) < 2 or len(cols) < 2:
            continue
        if (len(rows) - 1) * (len(cols) - 1) < cfg.table_min_cells:
            continue

        table_rows, table_confs = [], []
        for r0, r1 in zip(rows, rows[1:]):
            if r1 - r0 < 12:
                continue
            cells, confs = [], []
            for c0, c1 in zip(cols, cols[1:]):
                if c1 - c0 < 12:
                    continue
                # Inset must scale with the image: a 2px inset leaves the ruling
                # line inside the crop once the page has been upscaled, and a
                # residual border reliably turns "12" into "Wo".
                inset = max(3, int(min(r1 - r0, c1 - c0) * 0.08))
                cell = gray[y + r0 + inset:y + r1 - inset,
                            x + c0 + inset:x + c1 - inset]
                text, conf = _read_cell(cell, cfg)
                cells.append(text)
                confs.append(conf)
            if cells:
                table_rows.append(cells)
                table_confs.append(confs)

        if table_rows:
            tables.append({
                "bbox": (x, y, x + cw, y + ch),
                "rows": table_rows,
                "cell_confidence": table_confs,
                "shape": [len(table_rows), max(len(r) for r in table_rows)],
            })
    return tables


def _read_cell(cell: np.ndarray, cfg: Config) -> tuple[str, float]:
    """Return (text, mean word confidence). Confidence is the only thing that
    can catch a cell that produced confident-looking nonsense."""
    if cell.size == 0 or min(cell.shape) < 6:
        return "", -1.0
    # Tesseract does better with clear margin around the text.
    padded = cv2.copyMakeBorder(cell, 12, 12, 12, 12,
                                cv2.BORDER_CONSTANT, value=255)
    # psm 6 = assume a single uniform block of text, which is what a cell is.
    data = pytesseract.image_to_data(
        padded, lang=cfg.tesseract_lang, config="--psm 6",
        output_type=pytesseract.Output.DICT,
    )
    parts, confs = [], []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if word and conf >= 0:
            parts.append(word)
            confs.append(conf)
    if not parts:
        return "", -1.0
    return " ".join(parts), float(np.mean(confs))


def integrity(table: dict, cfg: Config) -> tuple[bool, list[str]]:
    """Cheap sanity checks. A table that fails these is flagged, not emitted
    silently as broken Markdown."""
    problems = []
    rows = table["rows"]
    widths = {len(r) for r in rows}
    if len(widths) > 1:
        problems.append(f"ragged rows: cell counts {sorted(widths)}")
    if rows and all(not c.strip() for c in rows[0]):
        problems.append("header row is empty")
    filled = sum(1 for r in rows for c in r if c.strip())
    total = sum(len(r) for r in rows)
    if total and filled / total < 0.4:
        problems.append(f"only {filled}/{total} cells produced text")

    weak = [
        f"r{i}c{j}={rows[i][j]!r}"
        for i, row in enumerate(table.get("cell_confidence", []))
        for j, conf in enumerate(row)
        if 0 <= conf < cfg.cell_conf_min
    ]
    if weak:
        problems.append(f"low-confidence cells: {', '.join(weak[:6])}")
    return (not problems), problems
