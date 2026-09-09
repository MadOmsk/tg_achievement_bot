# Tables & nicknames — how the lists are built (draft, issue #41)

Companion to [ui_screens_users.md](ui_screens_users.md) /
[ui_screens_admin.md](ui_screens_admin.md), which just say **"→ table: `<id>`"**
wherever a list goes. This file is the source of truth for each `<id>`'s source
query, scope, sort, cap, and which nickname rule its rows use. Verified against
the code (2026-09-09) — update in the same change as the underlying query or
fallback chain.

## Nickname rules

Five different chains, not one shared function everywhere:

| # | Chain | Used by |
|---|-------|---------|
| **A** | `@username` → имя+фамилия → Xbox-ник → *(см. ниже)* | `/stats`, `/who`, `/panel` headers |
| **B** | ник самой платформы (Xbox/Steam/PSN), без Telegram-имени | построчно на `/stats`, `/panel`; публикации; блоки в карточке юзера |
| **C** | ник платформы, где виден онлайн → имя+фамилия → username без `@` → id | только `/online` |
| **D** | Xbox-ник → Steam-ник → PSN-ник → id | только список юзеров в админке |
| **E** | только `users.gamertag`, без Steam/PSN вообще | `/recent`, оба лидерборда `/summary`, список подписчиков в карточке чата |

**A — Telegram identity** (`services/achievements.py::telegram_identity`).
"Кто этот человек", а не привязка к платформе.
- `/stats`, `/who` (`handlers/chat.py::_display_name`/`_who_label`): хвост цепочки —
  ник любой подключённой платформы, затем `id<tg_id>`.
- `/panel` (`handlers/panel.py::_panel_identity`): хвост — сразу `id<tg_id>`, без
  подстановки платформенного ника (экран виден только владельцу).

**B — ник самой платформы.** Xbox-гейм­тег / Steam persona / PSN online ID, у
каждой свой мини-фолбэк (заглушка "нет имени" для Xbox, сырой id для Steam/PSN).
Telegram-имя тут не участвует вообще.
- `services/achievements.py::platform_header_lines` — построчные блоки `/stats` и `/panel`.
- `services/achievements.py::format_single`/`format_digest` — текст публикации.
- `handlers/admin.py::_xbox_admin_block`/`_steam_admin_block`/`_psn_admin_block`.

**C — ник по онлайну, никогда `@mention`** (`services/online_view.py::_row_name`).
Ник платформы, которая сейчас "выигрывает" по присутствию (в игре — приоритет,
иначе последняя реально отслеженная), иначе имя+фамилия, иначе голый username
**без `@`** — таблица автообновляется каждые пару минут, живой `@mention` пинговал
бы человека на каждое обновление.

**D — приоритет админского списка** (`handlers/admin.py`, только список юзеров
на главной админ-панели). Telegram-имя нигде не участвует.

**E — только Xbox-гейм­тег, без фолбэка.** `/recent`, оба лидерборда `/summary` и
подписчики в карточке чата читают `users.gamertag` напрямую — у Steam/PSN-only
человека там заглушка ("кто-то" / `id<tg_id>`), а не его реальный ник.
> ⚠️ Похоже на тот же класс бага, что чинили в `/panel` (2026-09-09). Не
> исправлено — ждёт решения, к какой цепочке (A или B) это привести.

## Таблицы

| id | Источник | Кто попадает | Сортировка | Лимит |
|---|---|---|---|---|
| `stats-recent-games` | `repo.recent_games()` × каждая платформа, объединено | владелец карточки | счёт ↓, число ач. ↓ | `stats_games_limit` (0 = без лимита) |
| `recent-achievements` | `repo.chat_recent()` | подписчики чата | `unlocked_at` ↓ | аргумент `N` команды |
| `online-presence` | `repo.chat_member_presence()` | подписчики ∪ `chat_seen` | играет → онлайн → офлайн, внутри уровня — `updated_at` ↓ | — |
| `summary-leaderboard-day` / `-month` | `repo.chat_member_stats()` | все подписчики, **включая ноль** | счёт за период ↓ | `summary_top_limit` (0 = без лимита) |
| `summary-top-games-month` | `repo.chat_top_games()` | игры, не люди | число ач./трофеев ↓ | `summary_top_limit` |
| `admin-user-list` | `repo.admin_users()` | подключён хоть на одной платформе | `is_excluded` ↑, `last_online_at` ↓ | `PAGE_SIZE`/страница |
| `admin-chat-list` | `repo.admin_chats()` | все чаты | `is_active` ↓, название ↑ | — |
| `admin-chat-subscribers` | `repo.chat_subscriber_names()` | подписчики чата | по нику ↑ | — |

Ник каждой таблицы — по правилу из списка выше: `stats-recent-games` без ника (это
игры, не люди); `online-presence` → **C**; `admin-user-list` → **D**;
`recent-achievements`, оба `summary-leaderboard-*` и `admin-chat-subscribers` →
**E** (см. предупреждение выше).

### Особенности по конкретным таблицам

- **`stats-recent-games`** — окно: скользящие `RECENT_GAMES_DAYS` (30) дней,
  независимо от календарного месяца, на котором стоят счётчики выше. Одна игра на
  двух платформах = две строки (`title_id` + `platform`).
- **`recent-achievements`** — только подписчики (не общее "known member" множество
  `/online`), исключённые не попадают. Название ачивки скрыто спойлером при `is_secret`.
- **`online-presence`** — активность важнее свежести: "играет" всегда выше "в
  сети", `updated_at` решает только *внутри* одного уровня (иначе Xbox,
  опрошенный на секунду позже Steam, выглядел бы менее активным, хотя на деле
  играет прямо сейчас).
- **`summary-leaderboard-*`** — нулевые строки не скрываются: это отчёт, а не
  живая лента (#34). Бейдж `💎N` (редкие) — только в месячном блоке (#9), в
  дневном его нет; платформенная разбивка (`🟢 N · ⚫ N`) есть всегда.
- **`summary-top-games-month`** — группировка по `(title_id, platform)`, не по
  одному `title_id`: Steam appid и Xbox title_id — оба голые числа и могут
  совпасть случайно. PSN-строки несут ещё бронзу/серебро/золото/платину.
- **`admin-user-list`** — Steam/PSN-only человек не отфильтрован. Строка также
  показывает счётчик за сегодня/месяц (`achievement_counts_by_tg_id`, суммарно по
  платформам).

Админ-панель (главная) сама по себе — не таблица, а агрегаты
(`services/admin_view.py`: `repo.admin_users()` + `repo.admin_chats()`), сортировать/
ограничивать нечего.
