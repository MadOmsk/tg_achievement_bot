# Tables & nicknames — how the lists are built (draft, issue #41)

Companion to [ui_screens_users.md](ui_screens_users.md) and
[ui_screens_admin.md](ui_screens_admin.md): those two files lay out each screen and
just say **"→ table: `<name>`"** wherever a list/table goes. This file is the one
place that says how each named table is actually built — source, sort order,
grouping, truncation — and which nickname rule its rows use. Verified against the
current code (2026-09-09); update this file in the same change if the underlying
query or fallback chain changes.

## Nickname rules

Five different chains exist in the codebase today, not one shared function
everywhere. Each table/screen below points at one of these by letter.

- **A — Telegram identity** (`services/achievements.py::telegram_identity`):
  `@username` → first+last name → Xbox gamertag → *(caller-specific tail below)*.
  This is "who the person is", independent of any platform.
  - `/stats` header, `/who` picker (`handlers/chat.py::_display_name`/`_who_label`):
    tail falls back further to a connected platform's own display name (Steam or
    PSN, whichever is looked at first / whichever the row carries), then a bare
    `id<tg_id>` placeholder.
  - `/panel` header (`handlers/panel.py::_panel_identity`): tail falls straight to
    the bare `tg_id` — no platform-link fallback (the screen is only ever shown to
    its own owner, so a bare id is an acceptable last resort here).

- **B — platform's own nickname**: the gamertag / Steam persona name / PSN online
  ID stored for that platform, with its own small fallback (a "no name" placeholder
  for Xbox, or the raw external id for Steam/PSN) — never the Telegram identity.
  Used for: `/stats` and `/panel`'s own per-platform lines
  (`services/achievements.py::platform_header_lines`), every achievement/digest
  publish message (`services/achievements.py::format_single`/`format_digest`,
  fed by `gamertag`/`persona_name`/`online_id` from the poller that found the
  achievement), and the admin per-user card's platform blocks
  (`handlers/admin.py::_xbox_admin_block`/`_steam_admin_block`/`_psn_admin_block`).

- **C — presence-linked nickname, never an `@mention`**
  (`services/online_view.py::_row_name`, `/online` only): the nickname of
  whichever platform is currently "winning" presence for that row (the one being
  played, or — while offline — whichever platform has real tracked presence and
  was polled most recently); falls back to Telegram first+last name, then a bare
  username with no `@`, then `id<tg_id>`. The no-`@` rule is deliberate: this table
  auto-refreshes every few minutes, and a live `@mention` would ping that person's
  client on every refresh.

- **D — admin user-list priority chain** (`handlers/admin.py`, admin home's user
  list only): gamertag → Steam display name → PSN online ID → `id<tg_id>`. No
  Telegram identity anywhere in this one.

- **E — Xbox gamertag only, generic fallback**. `/recent`, both `/summary`
  leaderboards (day and month), and the admin chat-card's subscriber list all
  read `users.gamertag` directly with no Steam/PSN fallback at all — a
  Steam/PSN-only person shows as a placeholder ("кто-то" / `id<tg_id>`) in these
  three specifically, never their real nickname. **This looks like the same class
  of gap the `/panel` Xbox-only bug was** (2026-09-09 fix), just not yet audited
  here — flagged, not fixed, pending a decision on whether to unify it with rule A
  or B.

## `stats-recent-games` — /stats' "Игры за N дней"

`repo.recent_games(external_id, since, limit)`, called once per connected
platform (Xbox xuid, Steam id, PSN account id) via `asyncio.gather`
(`handlers/chat.py`), then merged into one ranked list — not one section per
platform. Sort: `gamerscore DESC, unlocked_count DESC` (a tie, e.g. every Steam
game having gamerscore 0, breaks on unlock count). Window: rolling
`RECENT_GAMES_DAYS` (30) days, independent of the month-calendar window the
counters above it use. Cap: the admin's `stats_games_limit` setting, `0` = no cap
(the list already lives inside a collapsible quote either way). One row per
`(title_id, platform)` — a game owned on two platforms gets two rows.

## `recent-achievements` — /recent

`repo.chat_recent(chat_id, limit)` (`db/repo/_messages.py`). Scope: chat
*subscribers* only (not `/online`'s broader "known member" set), excluded users
never appear. Sort: `unlocked_at DESC`. Cap: the `N` argument to `/recent`
(default from config). Nickname: **rule E**. Achievement name is spoiler-wrapped
when `is_secret`.

## `online-presence` — /online

`repo.chat_member_presence(chat_id)` (`db/repo/_chat_stats.py`), shared by the
command and the auto-refresh poller so both render identically. Scope: union of
chat subscribers and anyone `chat_seen` has recorded writing in the chat — a
member doesn't need to be a publisher to show up here. Sort: playing-now first,
then online-idle, then offline/no-data — activity level always wins the sort;
`updated_at` is only a tiebreaker *within* the same level (deliberately not
"whichever platform was polled more recently", which would make an idle-Xbox
poll landing a moment later than an active-Steam one show the wrong state).
Nickname: **rule C**.

## `summary-leaderboard-day` / `summary-leaderboard-month`

`repo.chat_member_stats(chat_id, since, rare_threshold, until)`
(`poller/daily.py::_leader_row`, shared by `/summary`, `/summary_day`,
`/summary_month`, and the scheduled jobs). Scope: every chat subscriber, **including
a zero row** — this is a report, not the live feed, so someone who unlocked
nothing that period still appears (#34). Sort: by total achievement/trophy count
for the window (ties not specially broken beyond SQL's own order). Cap: the
admin's `summary_top_limit` setting, `0` = no cap. Per-row: platform breakdown
suffix (`🟢 N · ⚫ N`) always shown, plus a `💎N` rare-count tail — only in the
month block (`show_rare=True`), dropped in the day block (#9). Nickname: **rule E**.

## `summary-top-games-month`

`repo.chat_top_games(chat_id, since, limit)` (`db/repo/_chat_stats.py`). Not
"who" — `chat_member_stats`'s job above — but "which games", ranked by
achievements/trophies earned in that game by anyone subscribed, combined across
platforms. Grouped by `(title_id, platform)`, not `title_id` alone (a Steam appid
and an Xbox title_id are both bare numeric strings and not guaranteed disjoint).
Sort: unlock count `DESC`. Cap: same `summary_top_limit` setting as the
leaderboard above. PSN rows carry their own bronze/silver/gold/platinum tally
next to the count.

## Admin home — user counts (not a table)

Aggregate counts only (`services/admin_view.py`, built from `repo.admin_users()` +
`repo.admin_chats()`), not a per-row list — nothing to sort or cap.

## `admin-user-list`

`repo.admin_users()` (`db/repo/_admin.py`). Scope: every person connected on at
least one platform (Xbox, Steam, or PSN) — a Steam/PSN-only person is not filtered
out. Sort: `is_excluded ASC, last_online_at DESC` (excluded users sink to the
bottom, then most-recently-active first). Paginated, `PAGE_SIZE` rows per page.
Nickname: **rule D**. Each row also shows today's/month's achievement count
(`repo.achievement_counts_by_tg_id`, combined across platforms).

## `admin-chat-list`

`repo.admin_chats()` (`db/repo/_admin.py`). Sort: `is_active DESC, title ASC` —
active chats first, alphabetical within each group. No cap (admin-only screen,
expected to be small at this project's scale).

## `admin-chat-subscribers`

`repo.chat_subscriber_names(chat_id)` (`db/repo/_messages.py`). Sort:
alphabetical by gamertag. Nickname: **rule E** — same gap as `/recent` and
`/summary` above, same fix if/when one is made.
