"""Command line interface. Fully offline — no network calls anywhere."""
import argparse
import sys
from pathlib import Path

from . import render
from .config import DEFAULT
from .intake import IntakeError
from .pipeline import process

EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="imgdoc",
        description="Convert document images to LLM-ready Markdown or JSON, offline.",
    )
    p.add_argument("input", type=Path, help="image file or directory")
    p.add_argument("-o", "--output", type=Path, default=Path("out"),
                   help="output directory (default: ./out)")
    p.add_argument("-f", "--format", choices=["md", "json", "both"], default="both")
    p.add_argument("--lang", default=DEFAULT.tesseract_lang,
                   help="tesseract language code, e.g. eng, urd, eng+urd")
    p.add_argument("--psm", type=int, default=DEFAULT.tesseract_psm,
                   help="tesseract page segmentation mode (default 3)")
    p.add_argument("--dewarp", action="store_true",
                   help="attempt perspective correction; for photos of paper only")
    p.add_argument("--strict", action="store_true",
                   help="reject at the quality gate instead of attempting OCR")
    p.add_argument("--debug-dir", type=Path,
                   help="write the processed image used for OCR, for box verification")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    cfg = DEFAULT
    cfg.tesseract_lang = args.lang
    cfg.tesseract_psm = args.psm

    if args.input.is_dir():
        files = sorted(f for f in args.input.iterdir()
                       if f.suffix.lower() in EXTENSIONS)
    elif args.input.is_file():
        files = [args.input]
    else:
        print(f"error: {args.input} does not exist", file=sys.stderr)
        return 2

    if not files:
        print(f"error: no images found in {args.input}", file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)
    failures = 0

    for path in files:
        try:
            doc = process(path, cfg, args.dewarp, args.strict, args.debug_dir)
        except IntakeError as exc:
            print(f"SKIP  {path.name}: {exc}", file=sys.stderr)
            failures += 1
            continue

        stem = path.stem
        if args.format in ("json", "both"):
            (args.output / f"{stem}.json").write_text(render.to_json(doc),
                                                      encoding="utf-8")
        if args.format in ("md", "both"):
            (args.output / f"{stem}.md").write_text(render.to_markdown(doc),
                                                    encoding="utf-8")

        q = doc["quality"]
        print(f"{q['verdict'].upper():7} {path.name}  "
              f"conf={q['mean_ocr_confidence']}  blocks={len(doc['blocks'])}")
        for reason in q["reasons"]:
            print(f"        - {reason}")
        if q["verdict"] == "reject":
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
