"""Toolkit to manage "recall" feedback from people who recently took the test.

Workflow when a friend / channel member sends a list of remembered questions:

    1. Save the raw text into ``recalls/YYYY-MM-DD.txt`` (one phrase per line,
       blank lines and lines starting with ``#`` are ignored).
    2. ``python scripts/recall.py check recalls/YYYY-MM-DD.txt``
       Prints, for every phrase, the top matching questions in ``questions.json``
       so you can eyeball coverage before changing anything.
    3. ``python scripts/recall.py bump recalls/YYYY-MM-DD.txt``
       For every phrase, auto-picks the single best match (keyword-overlap score)
       and increments its ``recallCount``. Lines with no confident match are
       reported as MISSING and written into ``recalls/missing-YYYY-MM-DD.json``
       as a stub array of new question objects for you to fill in.
    4. Fill in the stubs (question text, options, correctAnswer, explanation),
       then ``python scripts/recall.py add recalls/missing-YYYY-MM-DD.json``
       to append them with ``recallCount=1``.
    5. ``python scripts/build_last_minute_exam.py`` regenerates the cheat-sheet
       ``last-minute-exam.md`` from all questions with ``recallCount >= 1``.

The same script also exposes::

    python scripts/recall.py top N      # print the N most-recalled questions
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "questions.json"

STOPWORDS = {
    "the", "a", "an", "of", "in", "is", "are", "to", "and", "or", "for",
    "what", "who", "which", "when", "where", "how", "do", "does", "did",
    "be", "by", "on", "as", "at", "this", "that", "these", "those", "it",
    "you", "your", "i", "we", "they", "with", "from", "have", "has", "had",
    "can", "could", "should", "would", "will", "us", "our", "their", "any",
    "all", "but", "if", "no", "not", "yes",
}


def _tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if t not in STOPWORDS and len(t) > 1}


def load_bank() -> list[dict]:
    bank = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    for q in bank:
        q.setdefault("recallCount", 0)
    return bank


def save_bank(bank: list[dict]) -> None:
    bank.sort(key=lambda q: q["id"])
    QUESTIONS.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")


def read_phrases(path: Path) -> list[str]:
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def score(phrase: str, q: dict) -> int:
    pt = _tokens(phrase)
    qt = _tokens(q["question"]) | _tokens(" ".join(q["options"])) | _tokens(q["explanation"])
    return len(pt & qt)


def best_matches(phrase: str, bank: list[dict], k: int = 3) -> list[tuple[int, dict]]:
    scored = [(score(phrase, q), q) for q in bank]
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [(s, q) for s, q in scored[:k] if s > 0]


def cmd_check(args: argparse.Namespace) -> int:
    bank = load_bank()
    phrases = read_phrases(args.file)
    for p in phrases:
        print(f"\n• {p}")
        ms = best_matches(p, bank)
        if not ms:
            print("    [MISSING]")
            continue
        for s, q in ms:
            tag = " HOT" if q.get("recallCount", 0) > 0 else ""
            print(f"    score={s}{tag} id={q['id']} recallCount={q.get('recallCount', 0)}: {q['question'][:100]}")
    return 0


def cmd_bump(args: argparse.Namespace) -> int:
    bank = load_bank()
    phrases = read_phrases(args.file)
    threshold = args.threshold
    missing: list[str] = []
    bumped: list[tuple[str, dict]] = []
    by_id = {q["id"]: q for q in bank}
    for p in phrases:
        ms = best_matches(p, bank, k=1)
        if not ms or ms[0][0] < threshold:
            missing.append(p)
            continue
        _, top = ms[0]
        by_id[top["id"]]["recallCount"] = top.get("recallCount", 0) + 1
        bumped.append((p, top))
    save_bank(bank)
    print(f"Bumped {len(bumped)} question(s); {len(missing)} missing.\n")
    for p, q in bumped:
        print(f"  +1  id={q['id']} (now {q['recallCount']}): {q['question'][:90]}  ← '{p[:60]}'")
    if missing:
        stub_path = ROOT / "recalls" / f"missing-{date.today().isoformat()}.json"
        stub_path.parent.mkdir(exist_ok=True)
        next_id = max((q["id"] for q in bank), default=9000) + 1
        stubs = []
        for i, p in enumerate(missing):
            stubs.append({
                "id": next_id + i,
                "question": p,
                "options": ["TODO option A", "TODO option B", "TODO option C"],
                "correctAnswer": 0,
                "category": "TODO",
                "isValuesQuestion": False,
                "explanation": "TODO explanation.",
                "source": "Recalled by test-takers",
                "recallCount": 1,
            })
        stub_path.write_text(json.dumps(stubs, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nMissing phrases written as editable stubs to: {stub_path}")
        print("Edit the file then run:  python scripts/recall.py add " + str(stub_path.relative_to(ROOT)))
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    bank = load_bank()
    existing = {q["id"] for q in bank}
    new = json.loads(args.file.read_text(encoding="utf-8"))
    if isinstance(new, dict):
        new = [new]
    added = 0
    for q in new:
        if any(str(v).startswith("TODO") for v in (q.get("category"), q.get("explanation"))) or any(
            isinstance(o, str) and o.startswith("TODO") for o in q.get("options", [])
        ):
            print(f"  ! skipping id={q.get('id')} – still has TODO placeholders")
            continue
        if q["id"] in existing:
            # update recallCount in place
            for b in bank:
                if b["id"] == q["id"]:
                    b["recallCount"] = max(b.get("recallCount", 0), q.get("recallCount", 1))
            print(f"  ~ existing id={q['id']} recallCount updated")
            continue
        q.setdefault("recallCount", 1)
        bank.append(q)
        existing.add(q["id"])
        added += 1
        print(f"  + added id={q['id']}: {q['question'][:90]}")
    save_bank(bank)
    print(f"\nTotal bank size: {len(bank)} (added {added}).")
    return 0


def cmd_top(args: argparse.Namespace) -> int:
    bank = load_bank()
    hot = sorted([q for q in bank if q.get("recallCount", 0) > 0], key=lambda q: (-q["recallCount"], q["id"]))
    for q in hot[: args.n]:
        print(f"  x{q['recallCount']:>2}  id={q['id']:>4}  [{q['category']}]  {q['question'][:100]}")
    print(f"\n{len(hot)} questions have been recalled at least once.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Manage recall feedback for the citizenship quiz bot.")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="Show top matches for each phrase in a recall file")
    pc.add_argument("file", type=Path)
    pc.set_defaults(func=cmd_check)

    pb = sub.add_parser("bump", help="Increment recallCount for best matches; report missing")
    pb.add_argument("file", type=Path)
    pb.add_argument("--threshold", type=int, default=2, help="Min keyword-overlap score to auto-match (default 2)")
    pb.set_defaults(func=cmd_bump)

    pa = sub.add_parser("add", help="Append new question objects from a JSON file")
    pa.add_argument("file", type=Path)
    pa.set_defaults(func=cmd_add)

    pt = sub.add_parser("top", help="List the most-recalled questions")
    pt.add_argument("n", type=int, nargs="?", default=30)
    pt.set_defaults(func=cmd_top)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
