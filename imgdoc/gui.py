"""Desktop UI for imgdoc. Standard library only, fully offline.

Run with:  python3 -m imgdoc.gui
"""
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import render
from .config import DEFAULT
from .intake import IntakeError
from .pipeline import process

FILETYPES = [
    ("Images", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp"),
    ("All files", "*.*"),
]

VERDICT_COLOUR = {"pass": "#1b7f37", "review": "#9a6700", "reject": "#b32d2e"}


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.doc = None
        self.path = None
        self.results = queue.Queue()

        root.title("imgdoc — image to LLM-ready text")
        root.geometry("880x640")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        bar = ttk.Frame(root, padding=(12, 12, 12, 6))
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Button(bar, text="Choose image…", command=self.choose).pack(side="left")

        self.dewarp = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Dewarp (photo of paper)",
                        variable=self.dewarp).pack(side="left", padx=(12, 0))

        self.fmt = tk.StringVar(value="md")
        for label, value in (("Markdown", "md"), ("JSON", "json")):
            ttk.Radiobutton(bar, text=label, value=value, variable=self.fmt,
                            command=self.show_output).pack(side="left", padx=(8, 0))

        self.file_label = ttk.Label(root, text="No file selected",
                                    padding=(12, 0), foreground="#666")
        self.file_label.grid(row=1, column=0, sticky="w")

        self.status = tk.Label(root, text="", anchor="w", justify="left",
                               padx=12, pady=6, wraplength=840)
        self.status.grid(row=2, column=0, sticky="ew")

        frame = ttk.Frame(root, padding=(12, 0))
        frame.grid(row=3, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.text = tk.Text(frame, wrap="word", font=("monospace", 10),
                            borderwidth=1, relief="solid")
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        actions = ttk.Frame(root, padding=12)
        actions.grid(row=4, column=0, sticky="ew")
        self.copy_btn = ttk.Button(actions, text="Copy to clipboard",
                                   command=self.copy, state="disabled")
        self.copy_btn.pack(side="left")
        self.save_btn = ttk.Button(actions, text="Save as…",
                                   command=self.save, state="disabled")
        self.save_btn.pack(side="left", padx=(8, 0))
        self.hint = ttk.Label(actions, text="", foreground="#666")
        self.hint.pack(side="left", padx=(12, 0))

    def choose(self):
        path = filedialog.askopenfilename(title="Choose an image",
                                          filetypes=FILETYPES)
        if not path:
            return
        self.path = Path(path)
        self.file_label.configure(text=str(self.path))
        self.set_status("Processing… (verification passes make this take a "
                        "few seconds)", "#444")
        self.text.delete("1.0", "end")
        self.copy_btn.state(["disabled"])
        self.save_btn.state(["disabled"])
        # The pipeline runs several OCR passes; off the UI thread so the
        # window stays responsive instead of appearing frozen.
        # Tk variables must be read on the UI thread; touching them from the
        # worker raises "main thread is not in main loop".
        dewarp = self.dewarp.get()
        threading.Thread(target=self.work, args=(dewarp,), daemon=True).start()
        self.root.after(100, self.poll)

    def work(self, use_dewarp: bool):
        try:
            doc = process(self.path, DEFAULT, use_dewarp=use_dewarp)
            self.results.put(("ok", doc))
        except IntakeError as exc:
            self.results.put(("error", str(exc)))
        except Exception as exc:  # surfaced rather than silently swallowed
            self.results.put(("error", f"{type(exc).__name__}: {exc}"))

    def poll(self):
        try:
            kind, payload = self.results.get_nowait()
        except queue.Empty:
            self.root.after(100, self.poll)
            return

        if kind == "error":
            self.doc = None
            self.set_status(f"Failed: {payload}", VERDICT_COLOUR["reject"])
            return

        self.doc = payload
        q = payload["quality"]
        lines = [f"{q['verdict'].upper()}   "
                 f"confidence {q['mean_ocr_confidence']}   "
                 f"{q['word_count']} words   {len(payload['blocks'])} blocks"]
        lines += [f"• {r}" for r in q["reasons"]]
        self.set_status("\n".join(lines), VERDICT_COLOUR[q["verdict"]])
        self.show_output()
        self.copy_btn.state(["!disabled"])
        self.save_btn.state(["!disabled"])

    def show_output(self):
        if not self.doc:
            return
        body = (render.to_markdown(self.doc) if self.fmt.get() == "md"
                else render.to_json(self.doc))
        self.text.delete("1.0", "end")
        self.text.insert("1.0", body)

    def copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.text.get("1.0", "end-1c"))
        self.hint.configure(text="Copied.")
        self.root.after(2000, lambda: self.hint.configure(text=""))

    def save(self):
        ext = self.fmt.get()
        path = filedialog.asksaveasfilename(
            defaultextension=f".{ext}",
            initialfile=f"{self.path.stem}.{ext}",
            filetypes=[(ext.upper(), f"*.{ext}")],
        )
        if not path:
            return
        Path(path).write_text(self.text.get("1.0", "end-1c"), encoding="utf-8")
        self.hint.configure(text=f"Saved to {path}")

    def set_status(self, text: str, colour: str):
        self.status.configure(text=text, fg=colour)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
