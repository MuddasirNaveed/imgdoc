"""Stage 8: renderers.

Both formats are derived from the same IR so they can never disagree.
Nothing here re-reads the image or re-runs OCR.
"""
import json


def to_json(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False)


def to_markdown(doc: dict) -> str:
    out: list[str] = []
    low_conf: list[str] = []

    for block in doc["blocks"]:
        kind = block["type"]

        if kind == "heading":
            out.append(f"{'#' * block.get('level', 2)} {block['text']}")
        elif kind == "key_value":
            out.append(f"- **{block['key']}**: {block['value']}")
        elif kind == "table":
            out.append(_table_md(block))
        else:
            out.append(block["text"])
        out.append("")

        # Tables carry a sentinel, not a real confidence, and their failing
        # cells are already named in the quality warnings.
        if kind == "table":
            continue
        if block.get("min_word_confidence", 100) < doc["_low_conf_threshold"]:
            low_conf.append(f"- {block['text'][:80]} (min word conf "
                            f"{block['min_word_confidence']})")

    body = "\n".join(out).strip()

    q = doc["quality"]
    front = [
        "---",
        f"source: {doc['source']['path']}",
        f"sha256: {doc['source']['sha256']}",
        f"verdict: {q['verdict']}",
        f"mean_ocr_confidence: {q.get('mean_ocr_confidence')}",
        "---",
        "",
    ]

    tail = []
    if low_conf:
        tail = ["", "", "## Low-confidence spans", ""] + low_conf
    if q["reasons"]:
        tail += ["", "", "## Quality warnings", ""] + [f"- {r}" for r in q["reasons"]]

    return "\n".join(front) + body + "\n".join(tail) + "\n"


def _table_md(block: dict) -> str:
    rows = block["rows"]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    padded = [r + [""] * (width - len(r)) for r in rows]
    header, *body = padded
    lines = [
        "| " + " | ".join(c.replace("|", "\\|") for c in header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |")
    if block.get("problems"):
        lines.append("")
        lines.append(f"<!-- table flagged: {'; '.join(block['problems'])} -->")
    return "\n".join(lines)
