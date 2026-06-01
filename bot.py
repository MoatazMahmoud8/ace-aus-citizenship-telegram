"""Daily Australian-citizenship quiz bot.

Designed to be invoked once an hour by GitHub Actions cron. On every run it:
  1. Computes today's "lucky hour" in Australia/Sydney time, deterministically
     derived from the date (so every run on the same day agrees).
  2. Exits quietly unless the current Sydney hour matches that lucky hour and
     we have not yet posted today.
  3. Picks a random previously-unsent question and posts it to the target
     Telegram chat as a quiz poll. Falls back to a plain text quiz message
     if the question has options longer than the Telegram poll limit.
  4. Updates ``state.json`` to record the post (the workflow commits it back
     to the repo).

Required env:
  TELEGRAM_BOT_TOKEN  Bot API token.
  TELEGRAM_CHAT_ID    @channelusername or numeric chat id.
Optional env:
  FORCE_SEND=1        Ignore the lucky-hour / already-posted-today gates.
  DRY_RUN=1           Do everything except call Telegram.
  QUIET_HOUR_START=9  AEST window start (inclusive, default 9).
  QUIET_HOUR_END=21   AEST window end (inclusive, default 21).
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent
QUESTIONS_PATH = ROOT / "questions.json"
STATE_PATH = ROOT / "state.json"
SYDNEY = ZoneInfo("Australia/Sydney")

POLL_QUESTION_LIMIT = 300
POLL_OPTION_LIMIT = 100
POLL_EXPLANATION_LIMIT = 200


def log(msg: str) -> None:
    print(f"[citizenship-bot] {msg}", flush=True)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            log("state.json corrupt; resetting")
    return {"sent": [], "last_post_date": None, "last_post_id": None}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def lucky_hour(date_str: str, start: int, end: int) -> int:
    """Deterministic hour in [start, end] derived from the date string."""
    digest = hashlib.sha256(date_str.encode("utf-8")).digest()
    span = end - start + 1
    return start + (digest[0] % span)


def pick_question(bank: list[dict], sent_ids: set[int]) -> dict | None:
    # Only pick questions that fit inside a Telegram quiz poll so the format
    # is consistent. Allow exhausting the pool by rotating back to the start.
    eligible = [
        q
        for q in bank
        if len(q["question"]) <= POLL_QUESTION_LIMIT
        and all(len(o) <= POLL_OPTION_LIMIT for o in q["options"])
        and 2 <= len(q["options"]) <= 10
        and 0 <= q["correctAnswer"] < len(q["options"])
    ]
    if not eligible:
        return None
    remaining = [q for q in eligible if q["id"] not in sent_ids]
    if not remaining:
        log("Question pool exhausted; resetting sent history")
        return random.choice(eligible)
    return random.choice(remaining)


def send_quiz_poll(token: str, chat_id: str, q: dict) -> dict:
    explanation = q["explanation"]
    recall = int(q.get("recallCount", 0))
    if recall > 0:
        # Prefix a "frequently asked" badge so members can spot known-hot
        # questions when the answer is revealed.
        badge = f"\U0001F525 Frequently asked in recent tests (x{recall}). "
        budget = POLL_EXPLANATION_LIMIT - len(badge)
        if budget < 20:
            badge = "\U0001F525 "
            budget = POLL_EXPLANATION_LIMIT - len(badge)
        if len(explanation) > budget:
            explanation = explanation[: budget - 1] + "\u2026"
        explanation = badge + explanation
    elif len(explanation) > POLL_EXPLANATION_LIMIT:
        explanation = explanation[: POLL_EXPLANATION_LIMIT - 1] + "\u2026"

    url = f"https://api.telegram.org/bot{token}/sendPoll"
    payload = {
        "chat_id": chat_id,
        "question": q["question"],
        "options": json.dumps(q["options"], ensure_ascii=False),
        "type": "quiz",
        "correct_option_id": q["correctAnswer"],
        "is_anonymous": True,
        "explanation": explanation,
        "explanation_parse_mode": "HTML",
    }
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram error: {data}")
    return data["result"]


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        log("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return 2

    force = os.environ.get("FORCE_SEND") == "1"
    dry_run = os.environ.get("DRY_RUN") == "1"
    start = int(os.environ.get("QUIET_HOUR_START", "9"))
    end = int(os.environ.get("QUIET_HOUR_END", "21"))

    now = datetime.now(SYDNEY)
    today = now.strftime("%Y-%m-%d")
    hour_now = now.hour
    target = lucky_hour(today, start, end)
    log(f"Sydney now={now.isoformat(timespec='minutes')} hour={hour_now} lucky_hour={target} window=[{start},{end}]")

    state = load_state()

    if not force:
        if state.get("last_post_date") == today:
            log("Already posted today; nothing to do.")
            return 0
        if hour_now != target:
            log("Not the lucky hour yet; nothing to do.")
            return 0

    if not QUESTIONS_PATH.exists():
        log(f"Missing {QUESTIONS_PATH}")
        return 2
    bank = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    sent_ids = set(state.get("sent", []))
    question = pick_question(bank, sent_ids)
    if question is None:
        log("No eligible questions found")
        return 2

    log(f"Picked question id={question['id']} category={question['category']}")

    if dry_run:
        log("DRY_RUN=1, skipping Telegram call")
        return 0

    result = send_quiz_poll(token, chat_id, question)
    msg_id = result.get("message_id")
    log(f"Posted message_id={msg_id}")

    # If we rotated past the end of the pool, reset the sent list.
    if len(sent_ids) >= len(bank):
        sent_ids = set()
    sent_ids.add(question["id"])
    state["sent"] = sorted(sent_ids)
    state["last_post_date"] = today
    state["last_post_id"] = question["id"]
    state["last_message_id"] = msg_id
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
