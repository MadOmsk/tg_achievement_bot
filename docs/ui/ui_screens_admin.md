# UI screens — super-admin panel (mockups, draft, issue #41)

Layout only, placeholders instead of real data — for editing. Nickname rules
and table contents are documented separately: see [tables.md](tables.md) for
"which rule builds `<nick>` here" (referenced below as **rule A/B/C/D/E**) and
for what actually goes into every `→ table:` line.

**Language convention** (2026-09-11): the prose in these files is English,
like everything else written in this project. The mockups themselves stay in
Russian, because that is what the bot renders by default and therefore what
you are comparing against when you test a screen. The bot also ships an
English locale (#48) — a screen set to it renders the same layout with the
`en` strings; nothing here changes shape per language except the column
padding, which is part of each locale's own `.ftl`.

**Roles** (2026-09-11): **super-admin** is the global operator, the Telegram
ids in `ADMIN_TG_IDS`, who owns every screen in this file. **Chat admin** is
the per-chat role issue #47 is about, which does not exist yet.

## Super-admin panel (home)

```
⚙️ Администрирование  ·  обновлено HH:MM

Пользователей: N (исключено: N)
  XBOX:  N (вход активен: N, без входа: N)
  Steam: N
  PSN:   N
Чатов:          N
API XBOX:  used/limit за окно
API Steam: used/limit за окно
Ключ Steam: <status>
Ключ PSN:   <status>
Запросов к PSN за сутки: N
```

Buttons:
```
[ 👤 Новые пользователи ]
[ ⚙️ Глобальные лимиты ]
[ 👥 Пользователи ]
[ 💬 Чаты ]
[ 🔑 Ключи платформ ]
```

## 🔑 Platform keys

```
🔑 Ключи платформ

Steam:     <set / not set>
PSN:       <set / not set>
Anthropic: <set / not set>
```

Buttons:
```
[ Задать/сменить ключ Steam ]
[ Убрать ключ Steam ]              (only when set)
[ Задать/сменить NPSSO PSN ]
[ Убрать NPSSO PSN ]               (only when set)
[ Задать/сменить ключ Anthropic ]
[ Убрать ключ Anthropic ]          (only when set)
[ ‹ Назад ]
```

"Set/change" puts the panel into a wait-for-one-text-message state carrying
the value itself. A secret is never shown back after saving — only the fact
that it is set.

## ⚙️ Global limits

```
⚙️ Глобальные настройки

<limit name>: <current value, or "без ограничения">
...
```

The limits, each its own button opening its own text input: rows in /summary
and in /stats' game list (0 = no limit), rows in /hltb results, /hltb page
size, system-message TTL (0 = off), /online auto-refresh interval and TTL,
and how often the Steam/PSN/Anthropic keys are checked.

## 👤 New users (defaults)

```
👤 Новые пользователи — настройки по умолчанию

Ачивки по умолчанию: <all/rare/hidden>
Профиль виден другим: <да/нет>
```

Buttons:
```
[ Ачивки по умолчанию: X ]   (tap cycles all → rare → hidden)
[ Профиль виден другим: да/нет ]  (toggle)
[ ‹ Назад ]
```

Applies only to *new* subscriptions/accounts — existing ones are untouched.

## User list

```
👥 Пользователи, стр. N/M

→ table: `admin-user-list`
```

Every row is a button opening that person's card.

## User card

```
👤 <name>, @<username>, tg_id N                           [rule A, full form]

🟢 XBOX: <nick>                                           [rule B]
XUID <id>
Вход: <status>, обновлён N назад
N достижений  ·  🏆 K  ·  сегодня N  ·  gamerscore G
В сети: N назад

⚫ Steam: <nick>                                           [rule B]
id <id>
Вход: <visibility>
N достижений  ·  🏆 K  ·  сегодня N
В сети: N назад

🔵 PSN: <nick>                                            [rule B]
account_id <id>
Вход: <visibility>
N трофеев  ·  сегодня N  ·  уровень L

Подписан: <chats>
```

The card's header is the one place in the project that shows all three
Telegram identifiers (name, `@username`, `tg_id`) at once. That is not the
same as rule A in tables.md — rule A picks *one* best name; this is the full,
untruncated form, specifically so the super-admin can search and cross-check.

Buttons:
```
[ 🚫 Исключить / ↩️ Вернуть ]
[ 🔄 Обновить XBOX ]   [ 🗑 Сброс XBOX ]     (only when connected)
[ 🔄 Обновить Steam ]  [ 🗑 Сброс Steam ]    (only when connected)
[ 🔄 Обновить PSN ]    [ 🗑 Сброс PSN ]      (only when connected)
[ ‹ К списку ]
```
"🗑 Сброс X" asks for a one-tap confirmation before wiping (the same pattern
as disconnecting a platform in [ui_screens_users.md](ui_screens_users.md)).

## Chat list

```
💬 Чаты, стр. N/M

→ table: `admin-chat-list`
```

Every row is a button opening that chat's card.

## Chat card

```
💬 <chat title>

Состояние:    <активен/отключён>
Публикуется:  N чел.
Порог редк.:  N%
Итог дня:     включён/выключен, в HH:MM
Часовой пояс: UTC±N
Мин. G:       N
Антиспам:     N ач. / M мин   (or "выключен")
Язык:         Русский / English

Подписаны: → table: `admin-chat-subscribers`
```

Buttons (2026-09-11 rework, user request — the rows that used to hold two to
four buttons side by side are entries now, each opening its own screen):
```
[ Порог редкости: N% ]
[ Итог дня: включён ▸ ]
[ Антиспам: N ач. / M мин ▸ ]
[ Язык: Русский ]
[ ⏸ Отключить чат / ▶️ Включить чат ]
[ 🗑 Сообщения ▸ ]
[ ‹ К списку ]
```

Each entry carries the state you would otherwise have to open the submenu to
read, so nothing is hidden — only uncrowded.

### Chat card → sub-screens

All three keep the chat card's own text above them, unchanged, so the chat's
whole state stays readable while its settings are being tuned. Every control
inside one redraws *that* screen rather than the root card.

```
Итог дня:                        Антиспам:
[ Итог дня: включён ]            [ Антиспам-фильтр: включён ]
[ Время итога: HH:MM (UTC±N) ]   [ Антиспам: N ач. ▸ ]  [ Окно: M мин ▸ ]
[ ‹ Назад ]                      [ ‹ Назад ]

🗑 Сообщения:
[ 🗑 Последнее ]
[ 🗑 Бота (24ч) ]
[ 🗑 Системные (24ч) ]
[ 🗑 Все системные ]
[ ‹ Назад ]
```

One wipe action per row: these are the destructive ones, and a cramped row of
four 🗑 buttons was exactly what made them easy to mistap.

**Language** is one shared value per chat, not per viewer — Telegram cannot
render a single group message differently for two people reading it, so
somebody has to decide for everyone. The super-admin today; a chat admin once
#47 exists.
