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

## Install

**Debian / Ubuntu** — grab the `.deb` from
[Releases](../../releases) and:

```bash
sudo dpkg -i imgdoc_1.0.0_amd64.deb
sudo apt-get install -f          # pulls in tesseract-ocr if missing
```

**From source** — any platform with Python 3.10+:

```bash
sudo apt install tesseract-ocr python3-tk    # or the equivalent for your OS
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Three ways to use it

### 1. The app window

```bash
imgdoc                      # installed
python3 -m imgdoc.gui       # from source
```

Pick an image, read the verdict, hit **Copy to clipboard**. Toggle between
Markdown and JSON without re-running anything.

### 2. Clipboard hotkey (the fast one)

Copy an image, press a hotkey, paste. The clipboard now holds Markdown instead
of a picture — so it works in claude.ai, ChatGPT, Slack, your editor, anywhere.

```bash
sudo apt install wl-clipboard libnotify-bin   # or xclip on X11
python3 -m imgdoc.clip
```

Bind it in **Settings → Keyboard → Custom Shortcuts**, command
`/opt/imgdoc/imgdoc --clip` (or a wrapper calling `python3 -m imgdoc.clip`),
shortcut of your choice.

Workflow: screenshot to clipboard → hotkey → wait for the notification → paste.

If the image is too poor to read, the clipboard is **left untouched** and the
notification tells you why. Replacing a good image with bad text would be the
worst possible outcome.

### 3. Terminal

```bash
imgdoc invoice.png                  # writes invoice.md and invoice.json
imgdoc ./scans -o ./out -f md       # a whole folder, Markdown only
imgdoc photo.jpg --dewarp           # photo of paper on a desk
```

Exit code is `1` if any image was rejected, so chain batch commands with `;`
rather than `&&`.

## What comes out

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

## Build it yourself

### Linux

```bash
pip install pyinstaller
pyinstaller imgdoc.spec --clean --noconfirm
./dist/imgdoc samples/clean.png -o /tmp/t     # smoke test
./packaging/build_deb.sh 1.0.0
sudo dpkg -i dist/imgdoc_1.0.0_amd64.deb
```

### Windows (.exe)

There is no prebuilt Windows binary yet. PyInstaller cannot cross-compile, so
the exe has to be produced on Windows. Two routes:

**On a Windows machine.** Install
[Python 3.12](https://www.python.org/downloads/) and
[Tesseract for Windows](https://github.com/UB-Mannheim/tesseract/wiki), then:

```powershell
git clone https://github.com/MuddasirNaveed/imgdoc.git
cd imgdoc
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt pyinstaller

# Tesseract is a C++ binary with no pip package, so it must be bundled.
mkdir vendor\tesseract\tessdata
copy "C:\Program Files\Tesseract-OCR\tesseract.exe" vendor\tesseract\
copy "C:\Program Files\Tesseract-OCR\*.dll" vendor\tesseract\
copy "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata" vendor\tesseract\tessdata\
copy "C:\Program Files\Tesseract-OCR\tessdata\osd.traineddata" vendor\tesseract\tessdata\

pyinstaller imgdoc.spec --clean --noconfirm
.\dist\imgdoc.exe samples\clean.png -o ci_out    # smoke test
```

`imgdoc.spec` detects Windows and pulls `vendor/tesseract` into the exe, so the
result is self-contained — no separate Tesseract install needed on the machine
that runs it.

**Or let GitHub build it.** Push a tag and the workflow in
`.github/workflows/release.yml` builds the Linux `.deb` and the Windows `.exe`
on GitHub's runners and attaches both to a Release:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

No Windows machine required. The Windows job is not yet verified against a real
run — expect to iterate on the first tag.

Binaries are around 110 MB, almost entirely OpenCV.

## Good to know

- Tables need visible ruling lines. Borderless tables are read as ordinary text.
- Panel borders in a screenshot can occasionally be mistaken for a table. The
  result gets flagged, but it still appears in the output.
- Bounding boxes refer to the processed image, not the original. Use
  `--debug-dir` to save what the OCR actually saw.
- English by default. Other languages need the matching Tesseract language pack
  and `--lang urd` (or whichever you install).
- Thresholds in `imgdoc/config.py` are sensible starting points, not tuned for
  your documents. Run a handful of your own files and adjust if needed.

## Licence

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Muddasir Naveed.
