# imgdoc

Converts document **images** to LLM-ready Markdown or JSON. Runs entirely on
your machine — no API keys, no network calls, no telemetry. The only external
dependency is the Tesseract binary from your distro's package manager.

The point is to spend the OCR and layout cost once, offline and deterministically,
so an LLM receives clean structured text instead of an image. That cuts tokens,
removes per-call variance, and makes the result auditable.

Handles scans, photos of paper, and screenshots (including dark mode) through
the same pipeline.

## Install

```bash
sudo apt install tesseract-ocr python3-tk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`python3-tk` is only needed for the GUI. Add language packs as required, e.g.
`tesseract-ocr-urd`.

## Use

Desktop UI — pick an image, read the verdict, copy the Markdown:

```bash
python3 -m imgdoc.gui
```

Command line:

```bash
python3 -m imgdoc.cli invoice.png                  # both formats into ./out
python3 -m imgdoc.cli ./scans -o ./out -f md       # a directory, Markdown only
python3 -m imgdoc.cli photo.jpg --dewarp           # photo of paper on a desk
python3 -m imgdoc.cli ./scans --strict             # refuse bad images
python3 -m imgdoc.cli img.png --debug-dir ./debug  # save the image OCR saw
```

Exit code is `1` if any image was rejected, `0` otherwise. Because of that,
chain batch commands with `;` rather than `&&`.

## Pipeline

| Stage | Module | What it does |
|---|---|---|
| Intake | `intake.py` | Format from bytes, EXIF orientation, SHA-256 |
| Polarity | `quality.py` | Detects and normalises light-on-dark input |
| Quality gate | `quality.py` | Blur, dark clipping, ink/paper contrast, glyph height |
| Geometry | `preprocess.py` | OSD rotation, optional dewarp, fine deskew |
| Photometric | `preprocess.py` | Shadow flattening, capped upscale |
| Tables | `tables.py` | Ruled-line detection, per-cell OCR with confidence |
| OCR | `ocr.py` | Word boxes and confidences retained |
| Structure | `structure.py` | Headings, paragraphs, key-values from relative geometry |
| IR | `pipeline.py` | One typed-block schema |
| Render | `render.py` | Markdown and JSON, both derived from the IR |

Markdown and JSON are views of the same intermediate representation, so they
cannot disagree. Nothing re-reads the image after OCR.

### Corrections are verified, not assumed

Deskew, OSD rotation, dewarp and illumination flattening are corrections for
photographed paper. Applied blindly to a screenshot they destroy it — a
screenshot has no skew, so the angle detector locks onto UI rectangles and
rotates crisp text through interpolation.

Each correction is therefore measured against a trial OCR pass on a
downsampled copy and kept only if it improves recognition. Rejected
corrections are listed in `preprocessing.rejected` so the output explains
itself.

This costs 2-4 extra downsampled OCR passes per image. On very large batches
that is real time; it is the price of handling scans and screenshots through
one pipeline without hand-tuned per-source thresholds.

## Verdicts

Every output carries `pass`, `review` or `reject` plus the reasons. This is the
point of the tool. An OCR pipeline that silently emits confident wrong numbers
is worse than one that refuses.

Tables are read cell by cell and each cell keeps its own confidence, so a
misread cell is flagged rather than rendered as clean Markdown.

A high mean confidence over very few words is not evidence of success, so
results below `min_words` do not let OCR override the pre-OCR checks.

## Calibration

`imgdoc/config.py` holds every threshold. **The defaults are starting points,
not calibrated values** — `blur_min` in particular is resolution-dependent.
Run the tool over 20-30 of your own images, read the reported `blur_score`,
`ink_contrast` and `median_text_height_px`, and set thresholds from what you
actually see.

Two known-noisy defaults: `cell_conf_min` (70.0) flags some cells that were
read correctly, and `text_height_min` (10) fires on most screenshots, where
8px screen text is perfectly legible.

## Verified behaviour

Measured against fixtures with known ground truth, on Tesseract 5.5.0 and
OpenCV 5.0.0:

| Fixture | Result |
|---|---|
| Clean 1000x1000 invoice | `review`, 9 blocks, table matches ground truth on all 20 cells |
| Same page rotated 6 degrees | deskew accepted, 93.1 mean confidence |
| Same page rotated 90 degrees | OSD rotation accepted, `pass`, 9 blocks |
| Dark-mode code screenshot | polarity inverted, 16 blocks at 86.8 |
| UI screenshot with chrome | bogus 180 degree flip rejected: 37.5 to 90.3 confidence |
| Gaussian blur radius 4 | `reject` at the quality gate |
| Downscaled to 300x300 | `reject`; misread cells flagged individually |

On a real 3801x1376 browser screenshot, rejecting a spurious 7.23 degree deskew
and the illumination flattening took the result from 1 word at 55.8 confidence
to 683 words at 81.0, against a manual best case of 82.9.

## Limitations

Real and deliberate, not oversights.

- **Borderless tables are not detected.** Only tables with visible ruling
  lines. A borderless table falls through to the prose extractor and its
  numbers are flattened into a paragraph.
- **UI chrome can be mistaken for a table.** Panel borders in a screenshot
  sometimes trip the ruled-line detector. The integrity check flags the
  result, but the spurious table still appears in the output.
- **Glare is not detected.** The exposure check catches underexposure and low
  ink/paper contrast only.
- **Bounding boxes are in processed-image space**, not original-image space.
  The geometry chain is not inverted. Use `--debug-dir` to save the processed
  image if you need to verify a box against pixels.
- **Heading levels come from relative glyph height only.** A document that
  signals hierarchy through bold or colour will come out flat.
- **Multi-column reading order is whatever Tesseract's page segmentation
  decides.** Not independently verified here.
- **Language defaults to `eng`.** Other languages need the matching Tesseract
  language pack and `--lang`. Accuracy for non-Latin scripts is untested.

## Licence

Add one before publishing if this is going public.
