# UI screens — current shape

Baseline reference for issue #41 (spec files instead of ad-hoc verbal
feedback). This document describes **what each major screen renders today**
(2026-09-08) — real examples pulled from production data, with the source
function and the formatting rules behind each line. It is not a proposal for
what any screen *should* become; it exists so a future change starts from an
accurate description of the current behavior instead of re-deriving it from
memory or from a messy chat message.

**Keep this current.** When a change alters a screen's structure or wording
rules, update its section here in the same change — the same "update the
source of truth alongside the change" rule CLAUDE.md applies to itself.

Every rendered example below is real bot output (HTML as sent to Telegram,
not a mockup), captured from a migrated copy of the production database.
Names, ids and numbers are real members of the community this bot serves.

---

## 1. `/stats [@who]`

**Source:** `bot/handlers/chat.py::_build_stats_text` (shared with `/who`'s
buttons — one implementation, so a player's card looks the same regardless
of how it was opened).

```
📊 <b>@madomsk</b>
🟢 XBOX: <a href="https://account.xbox.com/en-us/profile?gamertag=Mad%20Omsk">Mad Omsk</a>  ·  7 460 достижений  ·  🏆 9  ·  gamerscore 152 498
🔵 PlayStation: <a href="https://my.playstation.com/profile/SuperOmsk">SuperOmsk</a>  ·  17 трофеев  ·  уровень 5
⚫ Steam: <a href="https://steamcommunity.com/profiles/76561197981065056">Mad Omsk</a>  ·  1 678 достижений  ·  🏆 5

Сегодня:   0 достижений
За месяц:  5 достижений (🟢 1 · ⚫ 4) (+10 G)

<b>Игры за 30 дней</b>
<blockquote expandable>1. 🟢 Dispatch — 13 ач. (+360 G)
2. 🟢 Wobbly Life — 4 ач. (+80 G)
...</blockquote>
```

A Steam/PSN-only person (no Xbox) gets the same shape with the Xbox line
simply absent — `_build_stats_text` used to require `target.xuid`, fixed
2026-09-08:

```
📊 <b>@keimaks</b>
🔵 PlayStation: kmaks90  ·  242 трофея  ·  уровень 73

Сегодня:   7 достижений
За месяц:  20 достижений

<b>Игры за 30 дней</b>
<blockquote expandable>1. 🔵 Marvel's Spider-Man Remastered — 17 ач.
...</blockquote>
```

Line by line:

- **Header** — the person's Telegram identity (`@username` > first+last name
  > a connected platform's own name as a last resort), never a bare id.
  Never an inline link itself.
- **One line per connected platform** — `services/achievements.py::
  platform_header_lines`, shared with `/panel`'s own header. Xbox: gamertag
  (linked to the Xbox profile when `show_profile_links` is on for *this
  card's owner*), lifetime achievement count, 🏆 + completed-games count
  (only shown when nonzero), gamerscore. Steam/PSN: nickname (linked to the
  platform profile), lifetime count (worded "trophies" for PSN via
  `plural_trophies`, "achievements" elsewhere), 🏆 + platinum count for PSN
  (only when nonzero) or completed-games count for Steam, and PSN's own
  cached account level.
  - **Known inconsistency:** this platform-line order is whatever
    `repo.platform_links_of()` returns (Steam/PSN insertion order — no
    `ORDER BY`), so it is not guaranteed to be Xbox→Steam→PSN the way the
    admin card and `/panel` both explicitly order it. Not treated as a bug
    yet; worth a decision if a spec is written for this screen.
- **Сегодня / За месяц** — cross-platform totals (`plural_achievements`,
  always "achievements" even for an all-PSN total — a *combined* count is
  never platform-specific wording). `За месяц` is the calendar month, not a
  rolling 30 days (#14). A platform breakdown suffix (`🟢 3 · ⚫ 4`) only
  appears when more than one platform contributed that window; gamerscore
  suffix only when nonzero.
- **Игры за 30 дней** — a rolling 30-day window (explicitly labelled,
  distinct from the calendar-month counters right above it), one combined
  ranked list across every connected platform, sorted by gamerscore then
  unlock time. Xbox/Steam show gamerscore (skipped at 0), PSN shows nothing
  extra (already labelled "ач." — trophy count — no per-tier detail here).

---

## 2. `/panel` (private, own screen only)

**Source:** `bot/handlers/panel.py::render_panel`.

```
👤 @madomsk
🟢 XBOX: Mad Omsk  ·  7 460 достижений  ·  🏆 9  ·  gamerscore 152 498
⚫ Steam: Mad Omsk  ·  1 678 достижений  ·  🏆 5
🔵 PlayStation: SuperOmsk  ·  17 трофеев  ·  уровень 5

Вход XBOX:   ✅ активен
Вход Steam:  Mad Omsk  ·  ❓ не проверено
Вход PSN:    SuperOmsk  ·  ❓ не проверено
Публикация:  ✅ в «XBOX CG», «test chat»
Сейчас:      не в сети (4 мин назад)

Часовой пояс: UTC+5
```

- **Header** — identity + the same per-platform lines `/stats` uses
  (`platform_header_lines`, `show_links=False`: this screen's names were
  never inline links, the keyboard's own "Profile" buttons cover that).
  Here the order genuinely is Xbox→Steam→PSN, because the caller
  (`_panel_header_lines`) builds `platform_links` as an explicit
  `(steam_link, psn_link)` tuple rather than trusting DB row order — unlike
  `/stats` above.
- **Вход XBOX** — token status (`✅ активен` / `⚠️ требуется повторный вход`
  / `— отключён`), no ago-suffix for Xbox's own row (unlike the admin card's
  Xbox line, which does show one).
- **Вход Steam / Вход PSN** — nickname + achievement/trophy *visibility*
  status (`services/achievements.py::visibility_status_text`, shared with
  the admin card): `✅ ачивки видны`, `⚠️ ачивки скрыты`, or `❓ не проверено`
  for a link never actually checked, each with a "· N назад" suffix once a
  check has actually happened (`achievements_visible_checked_at`). This is
  the *last actually-checked* status (connect time or any backfill/resync
  since), never a live check made at render time.
- **Публикация** — which chats this person publishes to, or "нигде".
- **Сейчас** — Xbox-only presence (`_now_playing`) — PSN/Steam have no
  equivalent row here (Steam does have its own presence poller, but this
  screen has never surfaced it; PSN has no presence at all, issue #1).
- **Часовой пояс** — only the timezone row remains in the footer; the old
  24h/30d counters and "recent achievements" list are gone (#18) — the
  header above already covers achievements.
- The keyboard (not shown as text) carries one row per platform in fixed
  Xbox→Steam→PSN order — `[Profile, Disconnect]` when connected, one wide
  "Подключить" button when not (#33) — plus timezone / My chats / sync /
  `show_profile_links` toggle and per-chat subscription cards.

---

## 3. `/recent [N]`

**Source:** `bot/handlers/chat.py::recent` (header + `_recent_list`/
`_recent_row`), group-only.

```
🕘 <b>Последние достижения</b>
<blockquote expandable>💎 RideTheSun — 🟢 Breathedge, A complete idi... (+35 G · 4.45%) · 4 ч назад
💎 AllDreamss — 🔵 Call of Duty®: Black Ops II, Defender  (6.1%) · 22 ч назад
💎 RideTheSun — 🟢 S.T.A.L.K.E.R. 2: Heart of…, <span class="tg-spoiler">Contra spem spero</span> (+50 G · 0.05%) · 23 ч назад
...</blockquote>
```

One row per achievement, most recent first, across every connected
platform in the chat:

- **Badge** leads the line (`rarity_badge` — 💎 or 🏆, never empty, Xbox 360
  and unrated rows default to 🏆 rather than going unbadged).
- **Gamertag** — falls back to "кто-то" if somehow unresolved.
- **Platform icon + game name** (truncated), then the achievement name —
  wrapped in a `tg-spoiler` span when `is_secret`, so the name stays hidden
  behind a tap without revealing anything by its absence.
- **Tail** — `(+N G · X.XX%)` — gamerscore omitted when 0 (Steam always has
  none), rarity percent omitted when unknown, the whole parenthetical
  omitted when both are empty.
- **· N назад** — relative time.

No keyboard; replaces the chat's previous `/recent` message outright.

---

## 4. `/summary` — on demand, both blocks

**Source:** `bot/poller/daily.py::build_summary(repo, chat_id, threshold,
today, tz_offset_min=..., with_day=True, with_month=True)` — the exact same
function the scheduled daily job and `/summary_day`/`/summary_month` call,
just with both blocks turned on. This is also the shape the **scheduled
daily job** sends every day (day block only, see §5) plus what the
**month-end job** appends once a month (month block only, see §6) — see
CLAUDE.md's "Three summary shapes" for how the three jobs share this one
function.

```
📊 <b>Итог дня</b>, 8 сентября

<b>24 часа:</b> 5 достижений, +95 G
<blockquote expandable>1. RideTheSun — 3 достижения (🟢 3) (+95 G)
2. AllDreamss — 2 достижения (🔵 2) (+0 G)
3. Whalerider84 — 0 достижений (+0 G)
4. Mad Omsk — 0 достижений (+0 G)</blockquote>

<b>с 1 сентября:</b> 60 достижений, +1 670 G
<blockquote expandable>1. RideTheSun — 42 достижения 💎21 (🟢 42) (+1 440 G)
2. AllDreamss — 13 достижений 💎4 (🟢 5 · 🔵 8) (+220 G)
3. Mad Omsk — 5 достижений (🟢 1 · ⚫ 4) (+10 G)
4. Whalerider84 — 0 достижений (+0 G)</blockquote>

<b>Игры за месяц</b>
<blockquote expandable>1. 🟢 Rue Valley — 16 достижений (+715 G)
2. 🟢 S.T.A.L.K.E.R. 2: Heart of Chornobyl - Windows Edition — 15 достижений (+320 G)
3. 🟢 Breathedge — 9 достижений (+205 G)
4. 🔵 Call of Duty®: Black Ops II — 8 трофеев 🥇1 🥉7
5. 🟢 Denshattack! — 4 достижения (+120 G)
6. ⚫ G.O.P.O.T.A — 3 достижения
...</blockquote>
```

- **Header** — "Итог дня, <day> <month>" when the day block is present (see
  §5/§6 for the other two header shapes).
- **Day leaderboard** (`_section`, `show_rare=False`) — every subscribed
  member, even at 0 achievements (#34 — a quiet day still gets a report),
  ranked by count, with a per-platform breakdown suffix when more than one
  platform contributed. **No rare-pull count on this block** (#9) — the
  24h window was judged too short for a rare-pull callout to be worth it.
- **Month leaderboard** (`_section`, `show_rare=True`) — same shape, but
  *does* show a 💎N rare-pull count next to a member's total, and its own
  header names the actual month ("с 1 сентября", #6/#14) rather than a
  generic "этот месяц" — the label is re-derived from the cutoff every
  time, so it never needs a month-boundary special case.
- **Games block** (month-only, #7) — every game the chat's subscribed
  members played that month, ranked by combined achievements/trophies
  earned in it (not who earned them — that's the leaderboard's job).
  Leads with the platform icon; Xbox/Steam show gamerscore (skipped when
  0, `score_suffix`); PSN shows a per-tier trophy breakdown
  (`TROPHY_TIER_BADGE`: 🏆 platinum, 🥇 gold, 🥈 silver, 🥉 bronze, each
  skipped when 0) instead of gamerscore.
- A truncated leaderboard (over the admin-configured `summary_top_limit`)
  gets a "Показать всех" button under that block; not shown when nothing
  was truncated (this render had nothing to truncate, hence no keyboard at
  all here).

---

## 5. `/summary_day` — day block only

**Source:** same `build_summary`, `with_day=True, with_month=False`.
Hidden from `/help` and `chat-help-text` — a diagnostic entry point for the
#14 block split, not meant for everyday use alongside `/summary` itself.
This is also exactly what the **scheduled daily job** sends every day.

```
📊 <b>Итог дня</b>, 8 сентября

<b>24 часа:</b> 5 достижений, +95 G
<blockquote expandable>1. RideTheSun — 3 достижения (🟢 3) (+95 G)
2. AllDreamss — 2 достижения (🔵 2) (+0 G)
3. Whalerider84 — 0 достижений (+0 G)
4. Mad Omsk — 0 достижений (+0 G)</blockquote>
```

Just the day block from §4, in isolation — no games block, no month
leaderboard, same header shape as the combined `/summary`.

---

## 6. `/summary_month` — month block only

**Source:** same `build_summary`, `with_day=False, with_month=True`. Also
hidden from the help text. This is also exactly what the **month-end job**
sends once a month (last calendar day, same scheduled time, its own
`daily_reports` marker, *in addition to* that day's daily summary).

```
📊 <b>Итоги за месяц</b>

<b>с 1 сентября:</b> 60 достижений, +1 670 G
<blockquote expandable>1. RideTheSun — 42 достижения 💎21 (🟢 42) (+1 440 G)
2. AllDreamss — 13 достижений 💎4 (🟢 5 · 🔵 8) (+220 G)
3. Mad Omsk — 5 достижений (🟢 1 · ⚫ 4) (+10 G)
4. Whalerider84 — 0 достижений (+0 G)</blockquote>

<b>Игры за месяц</b>
<blockquote expandable>1. 🟢 Rue Valley — 16 достижений (+715 G)
...</blockquote>
```

Note the **different header** — "Итоги за месяц" (plural "итоги", no date)
instead of §4/§5's "Итог дня, <date>" — `build_summary` picks the header
based on which blocks are actually present, not a fixed template per
caller.

---

## 7. Admin panel — home (`/admin`)

**Source:** `bot/services/admin_view.py::render_admin_home`. Self-refreshing
(`poller/admin_refresh.py`, same cadence as `service_health`).

```
⚙️ Администрирование  ·  обновлено 21:33

Пользователей: 7 (исключено: 0)
  XBOX:  6 (вход активен: 6, без входа: 0)
  Steam: 2
  PSN:   4
Чатов:          2
API XBOX (достижения):  3/100 за 15с · 12/300 за 5 мин
API Steam (достижения): 3/100 за 15с · 12/300 за 5 мин
Ключ Steam: ✅ жив, проверен только что
Ключ PSN:   ✅ жив, проверен только что
Запросов к PSN за сутки: 0
```

- **Header** — "обновлено HH:MM" always present, so a stalled auto-refresh
  is visible as a stale timestamp rather than silently frozen content.
- **Пользователей** — total + excluded, then per-platform linked counts;
  Xbox additionally splits "вход активен" (token alive) from "без входа"
  (token dead/revoked) — Steam/PSN have no token to be dead, so they're a
  bare count only (2026-09-05 follow-up: a Steam-only person used to be
  miscounted as a broken Xbox login).
- **Чатов** — active chats only.
- **API usage lines** — Xbox and Steam's own rate-limiter windows
  (`Fetcher.api_usage()` / `SteamFetcher.api_usage()`), formatted
  used/limit per window.
- **Ключ Steam / Ключ PSN** — the shared credential's live/dead status plus
  when it was last actually checked (`service_health`'s own tick), or a
  distinct "not configured" line when no key/NPSSO has ever been set at
  all (#17).
- **Запросов к PSN за сутки** — a bare count, no daily cap to compare
  against (PSN documents none).
- Keyboard: Новые пользователи / Лимиты / Пользователи / Чаты / Ключи —
  each opens its own sub-screen (not documented here; this file covers the
  home screen and the two per-entity cards below).

---

## 8. Admin panel — user card

**Source:** `bot/handlers/admin.py::_card`. Reached from the Users list.

```
👤 Igor, @madomsk, tg_id 188 022 193

🟢 XBOX: Mad Omsk
XUID 2533274829605736
Вход: ✅ активен, обновлён 11 мин назад
7 460 достижений  ·  🏆 9  ·  сегодня 0  ·  gamerscore 152 498
В сети: 4 мин назад

⚫ Steam: Mad Omsk
id 76561197981065056
Вход: ❓ не проверено
1 678 достижений  ·  🏆 5  ·  сегодня 0
В сети: 10 мин назад

🔵 PSN: SuperOmsk
account_id 980050590411556652
Вход: ❓ не проверено
17 трофеев  ·  сегодня 0  ·  уровень 5

Подписан: «XBOX CG», «test chat»
```

- **Header** — full Telegram identity at once (name, `@username`, and a
  plain `tg_id N` — never `@N`, a bare id is never a resolvable username).
  Unlike `/stats`' header (one best name), the admin needs everything
  visible for lookups.
- **One block per connected platform, fixed Xbox→Steam→PSN order**
  (2026-09-08 restructure), five lines each (four for PSN — no presence to
  show a fifth):
  1. `{icon} {PLATFORM}: {nickname}`
  2. platform id (`XUID ...` / `id ...` / `account_id ...`)
  3. status — Xbox: token status + "обновлён N назад"; Steam/PSN:
     `visibility_status_text` (shared with `/panel`, see §2) — deliberately
     does **not** repeat the nickname already on line 1
  4. achievements — lifetime count, 🏆/platinum count when nonzero,
     today's count, gamerscore (Xbox) or level (PSN)
  5. last online (Xbox/Steam only — PSN has no presence hook, issue #1)
- **Подписан** — every chat this person publishes to, or "нигде". The old
  combined "Ачивок (везде): ..." footer line that used to follow this is
  gone (2026-09-08) — each block above already has its own achievements
  line, the combined total added nothing beyond it.
- Keyboard (not shown): a 🔄 refresh + 🗑 reset button pair per connected
  platform, plus exclude/restore.

---

## 9. Admin panel — chat card

**Source:** `bot/handlers/admin.py::_chat`. Reached from the Chats list.

```
💬 XBOX CG

Состояние:    активен
Публикуется:  4 чел.
Порог редк.:  15%
Итог дня:     да, в 20:00
Часовой пояс: UTC+3
Мин. G:       0

Подписаны: AllDreamss, Mad Omsk, RideTheSun, Whalerider84
```

- **Header** — the chat's own title.
- **Settings block** — active/excluded state, subscriber count, this
  chat's rarity threshold, whether/when the daily summary fires, this
  chat's timezone offset, minimum gamerscore filter. Every value here is
  per-chat (`chat_settings`), not a global default.
- **Подписаны** — names of every subscribed member (gamertag/nickname, not
  full Telegram identity — this is a settings summary, not a lookup card).
- Keyboard (not shown): toggle active, edit threshold/time/timezone/min-G,
  delete-last, wipe-24h, back to the chats list.

---

## Shared building blocks referenced above

- `services/achievements.py::platform_header_lines` — the per-platform
  header line, shared by `/stats` and `/panel`.
- `services/achievements.py::visibility_status_text` — Steam/PSN
  achievement/trophy visibility wording + "when checked", shared by
  `/panel` and the admin user card.
- `services/achievements.py::score_suffix` — "(+N G)" or nothing at 0,
  used everywhere gamerscore is shown.
- `services/achievements.py::TROPHY_TIER_BADGE` / `COMPLETED_BADGE` — PSN's
  per-tier icons and the shared "100%-completed / platinum" 🏆.
- `services/achievements.py::plural_achievements` / `plural_trophies` —
  wording rule: "achievements" for anything combined or non-PSN,
  "trophies" only for a count that is entirely PSN's own.
- `poller/daily.py::build_summary` — composes the day/month/games blocks
  independently so their formatting can't silently drift apart (#14).
