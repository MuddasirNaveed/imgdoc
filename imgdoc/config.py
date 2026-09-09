"""All tunable thresholds live here.

IMPORTANT: these defaults are starting points, not calibrated values.
Run `imgdoc calibrate <dir>` on a sample of your own images and adjust.
"""
from dataclasses import dataclass


@dataclass
class Config:
    # --- quality gate ---
    blur_min: float = 100.0          # variance of Laplacian; below this = too blurry
    dark_clip_max: float = 0.35      # max fraction of pixels crushed to black
    ink_contrast_min: float = 60.0   # mean(paper) - mean(ink), Otsu-split
    text_height_min: int = 10        # px; below this OCR is unreliable

    # --- preprocessing ---
    text_height_target: int = 30     # upscale until median glyph height reaches this
    upscale_max: float = 4.0
    deskew_max_deg: float = 15.0     # larger angles are handled by OSD rotation, not skew
    illumination_blur: int = 51      # kernel for background estimation (must be odd)
    illumination_std_min: float = 12.0  # don't even try flattening below this variance
    trial_max_dim: int = 1200        # downsample size for the verification OCR pass
    trial_margin: float = 1.02       # a correction must beat baseline by this much
    max_megapixels: float = 25.0     # hard ceiling on the upscaled image

    # --- ocr ---
    tesseract_lang: str = "eng"
    tesseract_psm: int = 3           # 3 = automatic page segmentation
    word_conf_min: float = 40.0      # words below this are kept but marked low-confidence

    # --- structure ---
    heading_ratio: float = 1.25      # line height / median line height to count as heading
    heading_ratio_h1: float = 1.75
    kv_max_key_words: int = 6        # "Invoice number:" ok, a whole sentence is not

    # --- tables ---
    table_line_ratio: float = 0.4    # a ruled line must span this fraction of the region
    table_min_cells: int = 4
    cell_conf_min: float = 70.0      # cells below this are flagged for review

    # --- verdict ---
    conf_pass: float = 80.0          # mean word confidence for a "pass" verdict
    min_words: int = 20              # below this, mean confidence is not meaningful
    conf_review: float = 60.0        # below this = "reject"


DEFAULT = Config()
