# Capturing the interface from a running build

Builds [docs/ui/captured_production.md](../../docs/ui/captured_production.md):
what the bot **actually** draws — text, inline buttons, images — so the
mockups in `docs/ui/` have something to be checked against.

Nothing is sent and no network is touched: a real `Dispatcher` is assembled
with the real routers and middleware, and the `Bot` is given a session that
records each outgoing Telegram call instead of performing it. The database is
a copy, and it is rolled back between screens — the language button, the
toggles and subscribing all write, and otherwise the next screen renders from
data the capture itself produced.

The scripts run against whichever tree they are pointed at, so to capture the
deployed version do `git worktree add <dir> <production commit>` and pass that
directory as the first argument.

```bash
# 1. A copy of the database, and an environment for it. The production
#    FERNET_KEY stays on the server: the shared keys in the copy are
#    re-encrypted with placeholders (see the doc's own note).
python -c "import sqlite3;s=sqlite3.connect('data/prod-dump.db');d=sqlite3.connect('/tmp/pristine.db');s.backup(d)"
python -c "import sqlite3;s=sqlite3.connect('/tmp/pristine.db');d=sqlite3.connect('/tmp/capture.db');s.backup(d)"

# 2. Screens reachable by a command or a button
PRISTINE_DB=/tmp/pristine.db python scripts/ui_capture/capture_screens.py \
    <tree> /tmp/captured.json scripts/ui_capture/screens.json /tmp/.env.capture

# 3. Messages the bot sends on its own: publications, summaries, reminders
python scripts/ui_capture/capture_posts.py \
    <tree> /tmp/captured_posts.json /tmp/.env.capture

# 4. Markdown
python scripts/ui_capture/render_docs.py \
    docs/ui/captured_production.md /tmp/captured.json /tmp/captured_posts.json
```

Copy the database through `sqlite3`'s own backup rather than `cp`: these files
are in WAL mode, and a plain copy of one can come back malformed (it did).

`screens.json` is the list of screens to capture: `id`, an English title, the
command or `callback_data`, and which chat it happens in. A new screen is one
more entry.

`.env.capture` is an ordinary `.env` with a fake `BOT_TOKEN` (nothing leaves
the machine), the real super-admin in `ADMIN_TG_IDS`, `DB_PATH` pointing at
the copy, and any valid `FERNET_KEY`.

A screen that needs a live platform call cannot be captured — it lands in the
document as not building, with its error. That is also what catches real
breakage: this is how the dead "Обновить" and "Сброс" buttons in the user card
were found.
