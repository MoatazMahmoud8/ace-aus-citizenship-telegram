"""Sync the Expo app's TypeScript question files from the bot's questions.json.

For every question file under ``<app>/data/questions-*.ts`` this script:
  * Adds ``recallCount: N,`` to the existing question objects whose ids appear
    in the bot bank with ``recallCount > 0`` (in-place; only edits matching blocks).
  * Appends any questions whose ids are present in the bot bank but missing
    from any of the .ts files. The category determines the destination file.

Run from the bot repo:

    python scripts/sync_to_app.py /home/moataz/work/citizenship-app-build/data
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CAT_TO_FILE = {
    "australian_values": "questions-values.ts",
    "australia_and_its_people": "questions-australia.ts",
    "democratic_beliefs": "questions-democratic.ts",
    "government_and_law": "questions-government.ts",
}

# Matches "id: NNNN,"  (start of a question block)
ID_LINE_RE = re.compile(r"^(?P<indent> +)id:\s*(?P<id>\d+),\s*$", re.MULTILINE)


def patch_existing_blocks(text: str, recall_by_id: dict[int, int]) -> tuple[str, int]:
    """Insert/replace ``recallCount: N,`` inside every question block whose id
    is in ``recall_by_id``. Idempotent: if the field is already present, it is
    updated; otherwise it is inserted before the closing ``}`` of the block."""
    # Find each id-line, then walk forward to the matching closing-brace at the
    # same indentation level minus 2 spaces (since the block opens with `  {` and
    # field lines are indented one extra level).
    out: list[str] = []
    pos = 0
    edits = 0
    for m in ID_LINE_RE.finditer(text):
        qid = int(m.group("id"))
        if qid not in recall_by_id:
            continue
        recall = recall_by_id[qid]
        block_indent = m.group("indent")  # e.g. "    " for fields
        # find closing brace line `  },` two spaces less than block_indent
        close_indent = block_indent[:-2]
        close_re = re.compile(
            r"^" + re.escape(close_indent) + r"\},?\s*$",
            re.MULTILINE,
        )
        close_m = close_re.search(text, m.end())
        if not close_m:
            continue
        block_start, block_end = m.start(), close_m.start()
        block = text[block_start:block_end]

        # Already has recallCount?
        rc_re = re.compile(r"^" + re.escape(block_indent) + r"recallCount:\s*\d+,?\s*$", re.MULTILINE)
        if rc_re.search(block):
            new_block = rc_re.sub(f"{block_indent}recallCount: {recall},", block)
        else:
            # Insert before the closing brace (i.e. at the end of `block`).
            # Ensure block ends with newline.
            if not block.endswith("\n"):
                block += "\n"
            new_block = block + f"{block_indent}recallCount: {recall},\n"
        out.append(text[pos:block_start])
        out.append(new_block)
        pos = block_end
        edits += 1
    out.append(text[pos:])
    return "".join(out), edits


def render_new_question(q: dict) -> str:
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("'", "\\'")

    options = ", ".join(f"'{esc(o)}'" for o in q["options"])
    return (
        "  {\n"
        f"    id: {q['id']},\n"
        f"    question: '{esc(q['question'])}',\n"
        f"    options: [{options}],\n"
        f"    correctAnswer: {q['correctAnswer']},\n"
        f"    category: '{q['category']}',\n"
        f"    isValuesQuestion: {'true' if q['isValuesQuestion'] else 'false'},\n"
        f"    explanation: '{esc(q['explanation'])}',\n"
        f"    source: '{esc(q['source'])}',\n"
        f"    recallCount: {q.get('recallCount', 0)},\n"
        "  },\n"
    )


def append_new(text: str, new_qs: list[dict]) -> tuple[str, int]:
    if not new_qs:
        return text, 0
    rendered = "".join(render_new_question(q) for q in new_qs)
    # Insert before the closing `];` (the final one).
    pattern = re.compile(r"\n\];\s*\n", re.MULTILINE)
    matches = list(pattern.finditer(text))
    if not matches:
        raise RuntimeError("Could not find closing '];' in file")
    last = matches[-1]
    return text[: last.start()] + "\n" + rendered + text[last.start():], len(new_qs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", type=Path, help="Path to <app>/data/ folder")
    ap.add_argument("--bank", type=Path, default=Path(__file__).resolve().parent.parent / "questions.json")
    args = ap.parse_args()

    bank = json.loads(args.bank.read_text(encoding="utf-8"))
    by_cat: dict[str, list[dict]] = {c: [] for c in CAT_TO_FILE}
    for q in bank:
        by_cat.setdefault(q["category"], []).append(q)

    for cat, fname in CAT_TO_FILE.items():
        fp = args.data_dir / fname
        text = fp.read_text(encoding="utf-8")
        # Build the set of ids currently present
        present = {int(m.group("id")) for m in ID_LINE_RE.finditer(text)}
        cat_qs = by_cat.get(cat, [])
        recall_by_id = {q["id"]: q.get("recallCount", 0) for q in cat_qs if q.get("recallCount", 0) > 0 and q["id"] in present}
        text, edits = patch_existing_blocks(text, recall_by_id)
        # New questions to append: in bank-cat, not present in this file, and
        # not present in *any* file
        new_in_cat = [q for q in cat_qs if q["id"] not in present]
        text, added = append_new(text, new_in_cat)
        fp.write_text(text, encoding="utf-8")
        print(f"{fname}: bumped {edits}, appended {added} (now {len(present) + added} questions)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
