"""Stages 2-3: geometry and photometric correction.

Order matters: rotate (coarse) -> dewarp (optional) -> deskew (fine)
-> illumination -> upscale. Each step records what it did so the output
can explain itself.
"""
import cv2
import numpy as np
import pytesseract
from pytesseract import Output

from .config import Config


def osd_rotation(gray: np.ndarray) -> tuple[int, float]:
    """Tesseract's orientation detection. Handles the 90/180/270 cases.

    Raises TesseractError when there is too little text to decide, which is
    common on receipts and crops, so the caller treats failure as 'no rotation'.
    """
    try:
        osd = pytesseract.image_to_osd(gray, output_type=Output.DICT)
        return int(osd.get("rotate", 0)), float(osd.get("orientation_conf", 0.0))
    except Exception:
        return 0, 0.0


def rotate_90s(bgr: np.ndarray, degrees: int) -> np.ndarray:
    mapping = {
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }
    if degrees % 360 == 0:
        return bgr
    return cv2.rotate(bgr, mapping[degrees % 360])


def find_document_quad(bgr: np.ndarray):
    """Largest 4-point contour, for photos of paper on a contrasting surface.

    Returns None when no convincing quad is found. Conditional on purpose:
    forcing this on a screenshot or a tight crop destroys the image.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 60, 180)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    page_area = bgr.shape[0] * bgr.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        area = cv2.contourArea(contour)
        if area < page_area * 0.25:
            break
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)
    return None


def _order_quad(pts: np.ndarray) -> np.ndarray:
    """Order corners as top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype=np.float32,
    )


def dewarp(bgr: np.ndarray, quad: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = _order_quad(quad)
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if width < 50 or height < 50:
        return bgr
    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(_order_quad(quad), dst)
    return cv2.warpPerspective(bgr, matrix, (width, height))


def skew_angle(gray: np.ndarray, cfg: Config) -> float:
    """Dominant text angle from the minimum-area rect over a dilated text mask."""
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 3))
    mask = cv2.dilate(binary, kernel, iterations=2)
    coords = cv2.findNonZero(mask)
    if coords is None:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1]
    # The angle range returned by minAreaRect differs between OpenCV builds
    # (this one returns -84 where older docs describe [0, 90)). Normalise into
    # (-45, 45] rather than assuming a range.
    angle = (angle + 45) % 90 - 45
    if abs(angle) > cfg.deskew_max_deg:
        return 0.0
    return float(angle)


def rotate_fine(bgr: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.1:
        return bgr
    h, w = bgr.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    cos, sin = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w, new_h = int(h * sin + w * cos), int(h * cos + w * sin)
    matrix[0, 2] += new_w / 2 - w / 2
    matrix[1, 2] += new_h / 2 - h / 2
    return cv2.warpAffine(
        bgr, matrix, (new_w, new_h),
        flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE,
    )


def flatten_illumination(gray: np.ndarray, cfg: Config) -> tuple[np.ndarray, bool]:
    """Divide by a heavily blurred copy of itself to remove shadows.

    Only worth doing when the lighting is actually uneven. On a screenshot or
    a flatbed scan the background is already uniform, and dividing by it
    destroys the image rather than improving it.
    """
    k = cfg.illumination_blur | 1
    background = cv2.medianBlur(gray, k)
    if float(background.std()) < cfg.illumination_std_min:
        return gray, False
    flat = cv2.divide(gray, background, scale=255)
    return cv2.normalize(flat, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8), True


def trial_score(gray: np.ndarray, cfg: Config) -> float:
    """Cheap OCR score used to decide whether a correction helped.

    Runs on a downsampled copy so it costs a fraction of a real pass. The
    metric is the sum of word confidences, which rewards both reading more
    words and reading them more confidently.
    """
    scale = min(1.0, cfg.trial_max_dim / max(gray.shape))
    small = (cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
             if scale < 1.0 else gray)
    data = pytesseract.image_to_data(
        small, lang=cfg.tesseract_lang, config="--psm 3", output_type=Output.DICT
    )
    total = 0.0
    for text, conf in zip(data["text"], data["conf"]):
        try:
            c = float(conf)
        except (TypeError, ValueError):
            continue
        if text.strip() and c >= 0:
            total += c
    return total / 100.0


def run(bgr: np.ndarray, cfg: Config, text_height: float, use_dewarp: bool) -> tuple:
    """Apply the full correction chain. Returns (gray, steps_taken).

    Deskew, OSD rotation and illumination flattening are corrections for
    photographed paper. Applied blindly to a screenshot they destroy it, so
    each is measured against a trial OCR score and kept only if it improves
    recognition.
    """
    steps = {"rotate_deg": 0, "dewarped": False, "skew_deg": 0.0,
             "upscale": 1.0, "illumination_flattened": False, "rejected": []}

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    score = trial_score(gray, cfg)

    rotation, _ = osd_rotation(gray)
    if rotation:
        cand_bgr = rotate_90s(bgr, rotation)
        candidate = cv2.cvtColor(cand_bgr, cv2.COLOR_BGR2GRAY)
        cand_score = trial_score(candidate, cfg)
        # OSD is confidently wrong on UI screenshots, and an unchecked 180
        # flip turns every line upside down while still "succeeding".
        if cand_score > score * cfg.trial_margin:
            bgr, gray, score = cand_bgr, candidate, cand_score
            steps["rotate_deg"] = rotation
        else:
            steps["rejected"].append(f"OSD rotation {rotation} deg (no OCR gain)")

    if use_dewarp:
        quad = find_document_quad(bgr)
        if quad is not None:
            cand_bgr = dewarp(bgr, quad)
            candidate = cv2.cvtColor(cand_bgr, cv2.COLOR_BGR2GRAY)
            cand_score = trial_score(candidate, cfg)
            if cand_score > score * cfg.trial_margin:
                bgr, gray, score = cand_bgr, candidate, cand_score
                steps["dewarped"] = True
            else:
                steps["rejected"].append("dewarp (no OCR gain)")

    angle = skew_angle(gray, cfg)
    if abs(angle) >= 0.1:
        candidate = cv2.cvtColor(rotate_fine(bgr, angle), cv2.COLOR_BGR2GRAY)
        cand_score = trial_score(candidate, cfg)
        if cand_score > score * cfg.trial_margin:
            gray, score = candidate, cand_score
            steps["skew_deg"] = round(angle, 2)
        else:
            steps["rejected"].append(f"deskew {angle:.2f} deg (no OCR gain)")

    candidate, attempted = flatten_illumination(gray, cfg)
    if attempted:
        cand_score = trial_score(candidate, cfg)
        if cand_score > score * cfg.trial_margin:
            gray = candidate
            steps["illumination_flattened"] = True
        else:
            steps["rejected"].append("illumination flattening (no OCR gain)")

    if 0 < text_height < cfg.text_height_target:
        factor = min(cfg.text_height_target / text_height, cfg.upscale_max)
        megapixels = gray.shape[0] * gray.shape[1] / 1e6
        if megapixels * factor ** 2 > cfg.max_megapixels:
            factor = (cfg.max_megapixels / megapixels) ** 0.5
        if factor > 1.05:
            gray = cv2.resize(gray, None, fx=factor, fy=factor,
                              interpolation=cv2.INTER_CUBIC)
            steps["upscale"] = round(factor, 2)

    return gray, steps
