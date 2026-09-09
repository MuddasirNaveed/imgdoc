"""Stage 1: quality gate.

This is the only branch in the pipeline. Everything after it is a straight
line, so this is where a bad input gets stopped instead of silently
producing confident wrong text.
"""
import cv2
import numpy as np

from .config import Config


def blur_score(gray: np.ndarray) -> float:
    """Variance of the Laplacian. Higher = sharper. Scale-dependent, so
    calibrate on images of similar resolution to your own."""
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def is_light_on_dark(gray: np.ndarray) -> bool:
    """True when the page is light text on a dark background.

    Everything downstream — the glyph-height estimate, adaptive thresholding,
    Tesseract itself — assumes dark ink on light paper. A dark-mode screenshot
    breaks all three, so polarity is detected once and normalised.
    """
    t, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return float((gray < t).mean()) > 0.5


def exposure(gray: np.ndarray) -> tuple[float, float]:
    """Return (dark_clip_fraction, dynamic_range).

    Deliberately does NOT count blown highlights: a black-on-white document
    is legitimately 95%+ pure white, so treating white clipping as a fault
    rejects every clean scan. Glare detection needs local analysis and is
    not implemented — see README limitations.
    """
    dark = float(np.count_nonzero(gray <= 2)) / gray.size
    # Global percentiles are useless here: on a sparse-text page both the 5th
    # and 95th percentile land on white paper. Split ink from paper with Otsu
    # and measure the separation between the two populations instead.
    t, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    ink, paper = gray[gray < t], gray[gray >= t]
    if ink.size == 0 or paper.size == 0:
        return dark, 0.0
    return dark, float(paper.mean() - ink.mean())


def estimate_text_height(gray: np.ndarray) -> float:
    """Median height of connected components that look like glyphs.

    Cheap proxy that runs before OCR, so we can reject an image without
    paying for a full recognition pass.
    """
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 10
    )
    n, _, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return 0.0
    h = stats[1:, cv2.CC_STAT_HEIGHT]
    w = stats[1:, cv2.CC_STAT_WIDTH]
    area = stats[1:, cv2.CC_STAT_AREA]
    # Drop speckle and page-sized blobs; keep things shaped like characters.
    keep = (area > 8) & (h > 4) & (h < gray.shape[0] * 0.2) & (w < gray.shape[1] * 0.2)
    if not keep.any():
        return 0.0
    return float(np.median(h[keep]))


def assess(bgr: np.ndarray, cfg: Config) -> dict:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    blur = blur_score(gray)
    dark, dyn_range = exposure(gray)
    height = estimate_text_height(gray)

    reasons = []
    if blur < cfg.blur_min:
        reasons.append(f"blur score {blur:.1f} below threshold {cfg.blur_min}")
    if dark > cfg.dark_clip_max:
        reasons.append(f"{dark:.1%} of pixels crushed to black (underexposed)")
    if dyn_range < cfg.ink_contrast_min:
        reasons.append(
            f"ink-paper contrast {dyn_range:.0f} below {cfg.ink_contrast_min}; "
            "washed out or very low contrast"
        )
    if height < cfg.text_height_min:
        reasons.append(
            f"median glyph height {height:.1f}px below {cfg.text_height_min}px; "
            "OCR will not recover this"
        )

    return {
        "blur_score": round(blur, 2),
        "dark_clip_pct": round(dark * 100, 2),
        "ink_contrast": round(dyn_range, 1),
        "median_text_height_px": round(height, 1),
        "input_reasons": reasons,
        "input_ok": not reasons,
    }
