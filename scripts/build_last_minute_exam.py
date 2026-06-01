"""Generate ``last-minute-exam.md`` — a cheat-sheet of all questions that have
been recalled by real test-takers (``recallCount >= 1``), grouped by category
and sorted by frequency. Run after any ``recall.py bump`` / ``recall.py add``:

    python scripts/build_last_minute_exam.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "questions.json"
OUT = ROOT / "last-minute-exam.md"

CATEGORY_TITLE = {
    "australia_and_its_people": "Australia and Its People",
    "democratic_beliefs": "Democratic Beliefs",
    "government_and_law": "Government and the Law",
    "australian_values": "Australian Values",
}


def letter(i: int) -> str:
    return chr(ord("A") + i)


def main() -> int:
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    hot = [q for q in bank if q.get("recallCount", 0) > 0]
    hot.sort(key=lambda q: (-q["recallCount"], q["category"], q["id"]))

    grouped: dict[str, list[dict]] = defaultdict(list)
    for q in hot:
        grouped[q.get("category", "other")].append(q)

    lines: list[str] = []
    lines.append("# Last-minute citizenship exam")
    lines.append("")
    lines.append(
        f"> Generated {date.today().isoformat()}. "
        f"{len(hot)} questions that **real test-takers have reported seeing recently** "
        f"(out of {len(bank)} in the bank). "
        "Skim this the night before — these are the most likely to appear."
    )
    lines.append("")
    lines.append("Legend: 🔥 = number of times this question has been recalled by passers.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Quick index")
    lines.append("")
    for cat, qs in sorted(grouped.items()):
        lines.append(f"- [{CATEGORY_TITLE.get(cat, cat)} ({len(qs)})](#{CATEGORY_TITLE.get(cat, cat).lower().replace(' ', '-')})")
    lines.append("")
    lines.append("---")
    lines.append("")

    counter = 1
    for cat, qs in sorted(grouped.items()):
        lines.append(f"## {CATEGORY_TITLE.get(cat, cat)}")
        lines.append("")
        for q in qs:
            badge = "🔥" * min(q["recallCount"], 5)
            lines.append(f"### {counter}. {badge} {q['question']}")
            lines.append("")
            for i, opt in enumerate(q["options"]):
                mark = " ✅" if i == q["correctAnswer"] else ""
                lines.append(f"- **{letter(i)}.** {opt}{mark}")
            lines.append("")
            lines.append(f"> **Why:** {q['explanation']}")
            lines.append("")
            counter += 1
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} with {len(hot)} questions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
