"""Parse the .ts question banks from the citizenship-app project into questions.json.

Run once (or whenever the source files change):

    python scripts/parse_questions.py \
        --src /home/moataz/work/citizenship-app-build/data \
        --out questions.json
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

# Captures one Question object literal. Tolerant to single/double quotes and
# escaped quotes inside strings.
QUESTION_RE = re.compile(
    r"\{\s*"
    r"id:\s*(?P<id>\d+),\s*"
    r"question:\s*(?P<q_quote>['\"])(?P<question>(?:\\.|(?!(?P=q_quote)).)*)(?P=q_quote),\s*"
    r"options:\s*\[(?P<options>.*?)\],\s*"
    r"correctAnswer:\s*(?P<correct>\d+),\s*"
    r"category:\s*(?P<c_quote>['\"])(?P<category>[^'\"]+)(?P=c_quote),\s*"
    r"isValuesQuestion:\s*(?P<is_values>true|false),\s*"
    r"explanation:\s*(?P<e_quote>['\"])(?P<explanation>(?:\\.|(?!(?P=e_quote)).)*)(?P=e_quote),\s*"
    r"source:\s*(?P<s_quote>['\"])(?P<source>(?:\\.|(?!(?P=s_quote)).)*)(?P=s_quote)",
    re.DOTALL,
)

OPTION_RE = re.compile(
    r"(?P<quote>['\"])(?P<text>(?:\\.|(?!(?P=quote)).)*)(?P=quote)",
    re.DOTALL,
)


def _unescape(s: str) -> str:
    # Handle common JS escapes: \' \" \\ \n \t
    return (
        s.replace("\\'", "'")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
    )


def parse_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    out: list[dict] = []
    for m in QUESTION_RE.finditer(text):
        options = [
            _unescape(om.group("text"))
            for om in OPTION_RE.finditer(m.group("options"))
        ]
        out.append(
            {
                "id": int(m.group("id")),
                "question": _unescape(m.group("question")),
                "options": options,
                "correctAnswer": int(m.group("correct")),
                "category": m.group("category"),
                "isValuesQuestion": m.group("is_values") == "true",
                "explanation": _unescape(m.group("explanation")),
                "source": _unescape(m.group("source")),
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, type=Path, help="Folder with questions-*.ts")
    ap.add_argument("--out", required=True, type=Path, help="Output JSON path")
    args = ap.parse_args()

    bank: list[dict] = []
    seen_ids: set[int] = set()
    for f in sorted(args.src.glob("questions-*.ts")):
        parsed = parse_file(f)
        print(f"{f.name}: parsed {len(parsed)} questions")
        for q in parsed:
            if q["id"] in seen_ids:
                print(f"  ! duplicate id {q['id']} skipped")
                continue
            seen_ids.add(q["id"])
            bank.append(q)

    bank.sort(key=lambda q: q["id"])
    args.out.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(bank)} questions -> {args.out}")


if __name__ == "__main__":
    main()
