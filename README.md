# imgdoc

**Turn document images into clean text your LLM can actually read.**

Feed it a scan, a photo, or a screenshot. Get back Markdown or JSON — small,
structured, and ready to paste into any model.

Runs entirely on your machine. No API keys, no uploads, no internet.

---

## Why not just send the image?

Sending an image to a model costs a lot of tokens, and you pay that cost again
on every single message. The model also re-reads the layout from scratch each
time, so the same page can be interpreted differently from one call to the next.

imgdoc does the reading once, offline:

- **Smaller prompts.** A page of text is a fraction of the size of a page as an
  image, so you fit more context in and pay less for it.
- **Faster replies.** Less to process means the model starts answering sooner.
- **Same result every time.** Headings, tables, and key-value fields are
  resolved deterministically, not re-guessed on each call.
- **Nothing leaves your laptop.** Useful when the document is a contract, a
  payslip, or anything else you would rather not upload.

## Get started

```bash
sudo apt install tesseract-ocr python3-tk
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Open the app, pick an image, copy the result:

```bash
python3 -m imgdoc.gui
```

Or from the terminal:

```bash
python3 -m imgdoc.cli invoice.png              # writes invoice.md and invoice.json
python3 -m imgdoc.cli ./scans -o ./out -f md   # a whole folder, Markdown only
```

## What comes out

A photographed invoice goes in. This comes out:

```markdown
# PURCHASE INVOICE

- **Invoice No**: INV-2026-0417
- **Issued**: 04 September 2026
- **Vendor**: Northline Supplies Ltd

## Line items

| Item     | Qty | Unit  | Total |
| ---      | --- | ---   | ---   |
| Cable A  | 12  | 4.50  | 54.00 |
| Bracket  | 30  | 2.10  | 63.00 |

## Notes

Payment is due within thirty days of the invoice date.
```

Paste that straight into a chat, or use the JSON if you are building something
around it.

## Use it in your own code

```python
from pathlib import Path
from imgdoc.pipeline import process
from imgdoc.config import DEFAULT
from imgdoc import render

doc = process(Path("invoice.png"), DEFAULT)
markdown = render.to_markdown(doc)      # send this to your model
```

`doc` is a plain dict with typed blocks, so you can pull out just the tables or
just the key-value fields if that is all you need.

## It tells you when it is unsure

Bad OCR that looks confident is worse than no OCR. Every result carries a
verdict — `pass`, `review`, or `reject` — with the reasons attached:

```
REVIEW  invoice.png  conf=94.8  blocks=9
        - table [5, 4]: low-confidence cells: r1c0='Cable A'
```

Tables are read cell by cell and each cell keeps its own confidence score, so a
misread number gets flagged instead of quietly appearing in your output as
though it were correct.

## Works with messy input

Crooked scans, phone photos, 90-degree rotations, and dark-mode screenshots all
go through the same command. Corrections like deskew and rotation are applied
only when they measurably improve the result, so a screenshot does not get
"fixed" into something worse.

## Good to know

- Tables need visible ruling lines. Borderless tables are read as ordinary text.
- Bounding boxes refer to the processed image, not the original. Use
  `--debug-dir` to save what the OCR actually saw.
- English by default. Other languages need the matching Tesseract language pack
  and `--lang urd` (or whichever you install).
- Thresholds in `imgdoc/config.py` are sensible starting points, not tuned for
  your documents. Run a handful of your own files and adjust if needed.

## Licence

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Muddasir Naveed.
