# aceaus-citizenship-bot

Sends one Australian-citizenship-test (ACE question bank) quiz a day to the
Telegram group **[Australian citizenship test](https://t.me/ACEAUScitizenship)**,
at a random hour between **9am and 9pm AEST** (Australia/Sydney timezone, DST aware).

- 496 questions parsed from the `Our Common Bond` study guide categories
  (Australia and its people, Democratic beliefs, Government & the law,
  Australian values).
- Posted as a Telegram **quiz poll** (interactive: members tap an answer, the
  bot reveals the correct one with an explanation).
- Each question is sent at most once until the whole bank has cycled.

## How the random-time scheduling works (no servers, free)

GitHub Actions runs `bot.py` **every hour**. On each run the bot:

1. Computes Sydney-time today's "lucky hour" = `sha256(today) % 13 + 9` —
   the same value for every run that day, between 9 and 21.
2. If the current Sydney hour is not the lucky hour, exits silently.
3. If we have already posted today (recorded in `state.json`), exits silently.
4. Otherwise picks a random unsent question and posts the quiz.
5. Commits the updated `state.json` back to the repo so the next run sees it.

Result: exactly one post per day at a different, random-looking hour, with no
long-running job (well under GitHub's 6-hour limit) and full audit trail.

## One-time setup

1. **Create a GitHub repo** for this folder and push it:

   ```bash
   cd ~/aceaus-citizenship-bot
   git init && git add . && git commit -m "init"
   gh repo create aceaus-citizenship-bot --private --source=. --push
   ```

2. **Add the bot to the Telegram group** `@ACEAUScitizenship` and promote it to
   admin with "Post messages" permission. The same bot used by `newsbot_upload`
   (`8631395671:AAH…XmXuk`) can be reused — Telegram bots work in unlimited
   chats simultaneously.

3. **Resolve the chat id** (channels and public groups accept the `@handle`):

   ```bash
   # Try @handle first; if Telegram rejects it, fall back to numeric id.
   curl "https://api.telegram.org/bot<TOKEN>/getChat?chat_id=@ACEAUScitizenship"
   ```

   Use either `@ACEAUScitizenship` or the numeric `id` returned (e.g.
   `-1001234567890`).

4. **Set repo secrets** (Settings → Secrets and variables → Actions):

   - `TELEGRAM_BOT_TOKEN` — your bot token
   - `TELEGRAM_CHAT_ID` — `@ACEAUScitizenship` or the numeric id

5. **Enable Actions write permission** (Settings → Actions → General →
   Workflow permissions → "Read and write permissions"). Needed so the job can
   commit `state.json`.

## Test locally before going live

```bash
cd ~/aceaus-citizenship-bot
pip install -r requirements.txt

# Dry run — picks a question and prints it, no Telegram call:
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=@ACEAUScitizenship \
  FORCE_SEND=1 DRY_RUN=1 python bot.py

# Real test post (ignores lucky-hour gate):
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=@ACEAUScitizenship \
  FORCE_SEND=1 python bot.py
```

In GitHub: **Actions → Daily citizenship question → Run workflow → force=true**
will trigger an immediate test post.

## Refreshing the question bank

If you update the `.ts` source files in `citizenship-app-build/data`, re-run:

```bash
python scripts/parse_questions.py \
    --src /home/moataz/work/citizenship-app-build/data \
    --out questions.json
```

then commit the new `questions.json`.

## Files

| File | Purpose |
| --- | --- |
| `bot.py` | Picks one question and posts a Telegram quiz poll. |
| `questions.json` | The 496-question bank (parsed from the app source). |
| `state.json` | Tracks which questions have been sent and the last post date. |
| `scripts/parse_questions.py` | Regenerates `questions.json` from the `.ts` files. |
| `.github/workflows/daily-question.yml` | Hourly cron + commit-back. |
