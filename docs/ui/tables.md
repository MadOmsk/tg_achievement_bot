# Tables & nicknames — how the lists are built (draft, issue #41)

Companion to [ui_screens_users.md](ui_screens_users.md) /
[ui_screens_admin.md](ui_screens_admin.md), which just say **"→ table: `<id>`"**
wherever a list goes. This file is the source of truth for each `<id>`'s source
query, scope, sort, cap, and which nickname rule its rows use. Verified against
the code (2026-09-12) — update in the same change as the underlying query or
naming chain.

**Language convention** (2026-09-11): English, like the rest of what is
written in this project. Where a label below is quoted in Russian it is
because that is the literal string the bot renders in its default locale.

## Nickname rules

Two questions, two chains, reused everywhere — never a new one invented at a
call site (#51, 2026-09-12). This section used to list **five**, one per group
of screens, each defensible on its own; what that cost is written up in the
issue. `services/naming.py` is the only implementation.

| # | Question | Chain | Used by |
|---|----------|-------|---------|
| **P** | who is this person? | `Имя Фамилия` → `username` → any platform's nick (Xbox → Steam → PSN) → `id<tg_id>` | every screen that names a *person* |
| **X / S / N** | which account is this? | that platform's own chain (below) | every line that is about one platform |

**P — the person chain** (`person_name`, or `person_name_of` for the common
"a user row plus their links" shape). Digits last, the most human form first.
Used by `/stats`, `/who` and `/panel` headers; both `/summary` leaderboards;
`/recent`; the anti-flood digest header; the super-admin's user list; the
chat's subscriber list; `/subscribe`'s confirmation; and `/online` whenever
no platform nickname applies.

**No `@` anywhere.** A username renders bare. A live mention pings its
target, which is wrong in `/online` (it redraws every few minutes — this was
already reverted once, #38) and inconsistent everywhere else; one rule beats
remembering which screen is safe.

**The account chains**, same "digits last, newest form first" shape:

| Platform | Chain |
|---|---|
| **X** Xbox | `ModernGamertag` → `Gamertag` → XUID |
| **S** Steam | `personaname` → vanity → SteamID64 |
| **N** PSN | current `onlineId` → previous `onlineId` → `account_id` |

Each ends at an em dash when a platform gave us no name at all, because the
line it renders has to say *something*. Inside the person chain that dash is
an absence and is stepped over — handled in `person_name` itself, so passing
`xbox_nickname(...)` straight in is safe.

Used by: the per-platform lines of `/stats` and `/panel`
(`platform_header_lines`), the published achievement/trophy text
(`format_single`/`format_digest` — that message is scoped to one platform by
construction), the per-platform blocks of the super-admin's user card, and
`/online`'s rows **while someone is online**, where the nickname answers
"where are they right now" alongside the platform-coloured icon. An offline
row has no "where" left to answer, so it switches to **P** like everything
else (2026-09-12) — otherwise the same member reads as two different people
between this table and the summary above it.

The later steps of the Steam and PSN chains are near-unreachable in practice —
neither platform lets an account exist without a display name. They are the
rule, not an expected sight; a previous PSN online ID earns its place as
"formerly known as".

Xbox's profile **link** is built from the classic `Gamertag`, not from
whatever the chain displays: `account.xbox.com`'s own search is what has to
accept it.

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
| `admin-chat-subscribers` | `repo.chat_subscribers()` | the chat's subscribers | by the rendered name ↑ | — |
| `hltb-recent-suggestions` | `repo.chat_recent_games()` | games, not people | last played ↓ | `hltb_results_limit` |
| `hltb-search-results` | HowLongToBeat API (an external search, not the database) | games, not people | relevance, as HLTB returned it | `hltb_results_limit`, shown `hltb_page_size` at a time |

Each table's nickname follows one of the rules above: `stats-recent-games`
and both `hltb-*` have none (those are games, not people); `online-presence`
→ the account chain of whichever platform won on presence, falling through to
**P**; every other table here → **P**.

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
  currently **Xbox only** — Steam/PSN games never reach it. The same class of
  gap the naming chains had before #51 (a query that only knows how to answer
  for Xbox), one layer over; not fixed here.

The super-admin panel's home screen is not a table but a set of aggregates
(`services/admin_view.py`: `repo.admin_users()` + `repo.admin_chats()`), with
nothing to sort or cap.
