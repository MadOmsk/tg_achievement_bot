# Tables & nicknames — how the lists are built (draft, issue #41)

Companion to [ui_screens_users.md](ui_screens_users.md) /
[ui_screens_admin.md](ui_screens_admin.md), which just say **"→ table: `<id>`"**
wherever a list goes. This file is the source of truth for each `<id>`'s source
query, scope, sort, cap, and which nickname rule its rows use. Verified against
the code (2026-09-09) — update in the same change as the underlying query or
fallback chain.

**Language convention** (2026-09-11): English, like the rest of what is
written in this project. Where a label below is quoted in Russian it is
because that is the literal string the bot renders in its default locale.

## Nickname rules

Five different chains, not one shared function everywhere:

| # | Chain | Used by |
|---|-------|---------|
| **A** | `@username` → first+last name → Xbox nick → *(see below)* | `/stats`, `/who`, `/panel` headers |
| **B** | the platform's own nick (Xbox/Steam/PSN), no Telegram name at all | per-line on `/stats`, `/panel`; publications; the blocks in a user card |
| **C** | nick of whichever platform shows them online → first+last name → username without `@` → id | `/online` only |
| **D** | Xbox nick → Steam nick → PSN nick → id | the super-admin's user list only |
| **E** | `users.gamertag` alone, no Steam/PSN at all | `/recent`, both `/summary` leaderboards, the subscriber list on a chat card |

**A — Telegram identity** (`services/achievements.py::telegram_identity`).
"Who is this person", not which platform they linked.
- `/stats`, `/who` (`handlers/chat.py::_display_name`/`_who_label`): the tail of
  the chain is any connected platform's nick, then `id<tg_id>`.
- `/panel` (`handlers/panel.py::_panel_identity`): the tail is `id<tg_id>`
  directly, with no platform nick in between — this screen is only ever shown
  to its owner.

**B — the platform's own nick.** Xbox gamertag / Steam persona / PSN online ID,
each with its own small fallback (a "no name" placeholder for Xbox, the raw id
for Steam/PSN). The Telegram name plays no part here.
- `services/achievements.py::platform_header_lines` — the per-line blocks of
  `/stats` and `/panel`.
- `services/achievements.py::format_single`/`format_digest` — the published text.
- `handlers/admin.py::_xbox_admin_block`/`_steam_admin_block`/`_psn_admin_block`.

**C — nick by presence, never an `@mention`**
(`services/online_view.py::_row_name`). The nick of whichever platform
currently "wins" on presence (in a game takes priority, otherwise the last one
actually tracked), else first+last name, else the bare username **without
`@`** — this table auto-refreshes every few minutes, and a live `@mention`
would ping that person on every single refresh.

**D — the super-admin list's own priority** (`handlers/admin.py`, only the user
list on the panel's home screen). The Telegram name plays no part.

**E — Xbox gamertag only, no fallback.** `/recent`, both `/summary`
leaderboards and the chat card's subscriber list read `users.gamertag`
directly — a Steam/PSN-only person gets a placeholder there ("кто-то" /
`id<tg_id>`) rather than their real nick.
> ⚠️ This looks like the same class of bug that was fixed in `/panel`
> (2026-09-09). Not fixed — waiting on a decision about which chain (A or B)
> to bring it in line with.

## Tables

| id | Source | Who appears | Sort | Cap |
|---|---|---|---|---|
| `stats-recent-games` | `repo.recent_games()` per platform, merged | the card's owner | score ↓, achievement count ↓ | `stats_games_limit` (0 = no cap) |
| `recent-achievements` | `repo.chat_recent()` | the chat's subscribers | `unlocked_at` ↓ | the command's own `N` argument |
| `online-presence` | `repo.chat_member_presence()` | subscribers ∪ `chat_seen` | playing → online → offline, `updated_at` ↓ within a level | — |
| `summary-leaderboard-day` / `-month` | `repo.chat_member_stats()` | every subscriber, **zeroes included** | count for the window ↓ | `summary_top_limit` (0 = no cap) |
| `summary-top-games-month` | `repo.chat_top_games()` | games, not people | achievements/trophies ↓ | `summary_top_limit` |
| `admin-user-list` | `repo.admin_users()` | connected on at least one platform | `is_excluded` ↑, `last_online_at` ↓ | `PAGE_SIZE` per page |
| `admin-chat-list` | `repo.admin_chats()` | every chat | `is_active` ↓, title ↑ | — |
| `admin-chat-subscribers` | `repo.chat_subscriber_names()` | the chat's subscribers | by nick ↑ | — |
| `hltb-recent-suggestions` | `repo.chat_recent_games()` | games, not people | last played ↓ | `hltb_results_limit` |
| `hltb-search-results` | HowLongToBeat API (an external search, not the database) | games, not people | relevance, as HLTB returned it | `hltb_results_limit`, shown `hltb_page_size` at a time |

Each table's nickname follows one of the rules above: `stats-recent-games` has
none (those are games, not people); `online-presence` → **C**;
`admin-user-list` → **D**; `recent-achievements`, both `summary-leaderboard-*`
and `admin-chat-subscribers` → **E** (see the warning above).

### Per-table specifics

- **`stats-recent-games`** — window: a rolling `RECENT_GAMES_DAYS` (30) days,
  independent of the calendar month the counters above it use. One game on two
  platforms is two rows (`title_id` + `platform`).
- **`recent-achievements`** — subscribers only (not `/online`'s broader "known
  member" set); excluded people never appear. An achievement's name is hidden
  behind a spoiler when `is_secret`.
- **`online-presence`** — activity beats freshness: "playing" always outranks
  "online", and `updated_at` only decides *within* one level (otherwise an Xbox
  account polled a second later than a Steam one would look less active while
  actually being in a game right now).
- **`summary-leaderboard-*`** — zero rows are not hidden: this is a report, not
  a live feed (#34). The `💎N` rare badge appears in the month block only (#9),
  never the day's; the platform breakdown (`🟢 N · ⚫ N`) is always there.
- **`summary-top-games-month`** — grouped by `(title_id, platform)`, not by
  `title_id` alone: a Steam appid and an Xbox title_id are both bare numbers and
  can collide by accident. PSN rows also carry bronze/silver/gold/platinum.
- **`admin-user-list`** — a Steam/PSN-only person is not filtered out. The row
  also carries today's and this month's counts
  (`achievement_counts_by_tg_id`, summed across platforms).
- **`hltb-recent-suggestions`** — the same "known member" scope `/online` uses
  (subscribers ∪ `chat_seen`), but the source itself (`title_history`) is
  currently **Xbox only** — Steam/PSN games never reach it, another instance of
  the same class of gap as rule E above, likewise not separately fixed.

The super-admin panel's home screen is not a table but a set of aggregates
(`services/admin_view.py`: `repo.admin_users()` + `repo.admin_chats()`), with
nothing to sort or cap.
