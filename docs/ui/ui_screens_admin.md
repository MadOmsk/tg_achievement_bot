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

Every Russian word in a mockup below is a string from
`bot/locales/ru/LC_MESSAGES/*.ftl` and nothing else. **What is actually on
screen** is captured separately, from a running build:
[captured_production.md](captured_production.md) — a mockup here is the
decision, that file is the evidence.

**Platform order** (2026-09-13, owner decision): Xbox, PlayStation, Steam,
everywhere platforms are listed, from `constants.platform_display_rank`.

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
that it is set. That state is a screen of its own: the prompt says where to
get the value, and the only button is the way out.

```
<send the Steam Web API key in one message — where to get it:>
<https://steamcommunity.com/dev/apikey>
```
```
[ Отмена ]
```

## ⚙️ Global limits

```
⚙️ Глобальные настройки

<limit name>: <current value, or "без ограничения">
...
```

Buttons:
```
[ Строк в /summary: <value> ▸ ]
[ Игр в /stats: <value> ▸ ]
[ Результатов поиска и подсказок HLTB: N ▸ ]
[ Результатов на странице (HLTB): N ▸ ]
[ Автоудаление системных сообщений (мин): N ▸ ]
[ Интервал автообновления /online (мин): N ▸ ]
[ Автообновление /online, часов: N ▸ ]
[ Проверка ключей / автообновление /admin (мин): N ▸ ]
[ ‹ Назад ]
```

Each row carries its current value and opens its own one-message text input
(with its own "Отмена"), so the screen reads as a settings list rather than a
menu you have to walk to find out what is set. "0" shows as "без
ограничения" where zero means off.

The body text says out loud that the /summary and /stats lists can be made
unlimited, because both already live inside a collapsible blockquote — there
is nothing for a cap to protect.

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
👥 Пользователи  (page/pages)

→ table: `admin-user-list`

Колонки: когда был в сети · достижений сегодня / за месяц
```
```
[ <platform icons> <nick> ]      (one row per person, same order as the table)
[ <platform icons> <nick> ]
[ ‹ Назад ]   [ ‹ ]  [ › ]       (the arrows only when there is more than one page)
```

The list is printed twice on purpose: as text, where the columns line up and
can be read at a glance, and as one button per row, because a row has to be
tappable. The icons are that person's connected platforms, in the one display
order, plus ✅ for a live Xbox login.

## User card

```
👤 <name>, @<username>, tg_id N                           [rule A, full form]

🟢 XBOX: <nick>                                           [rule B]
XUID <id>
Вход: <status>, обновлён N назад
N достижений  ·  🏆 K  ·  сегодня N  ·  gamerscore G
В сети: N назад

🔵 PSN: <nick>                                            [rule B]
account_id <id>
Вход: <visibility>
N трофеев  ·  сегодня N  ·  уровень L

⚫ Steam: <nick>                                           [rule B]
id <id>
Вход: <visibility>
N достижений  ·  🏆 K  ·  сегодня N
В сети: N назад

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
[ 🔄 Обновить PSN ]    [ 🗑 Сброс PSN ]      (only when connected)
[ 🔄 Обновить Steam ]  [ 🗑 Сброс Steam ]    (only when connected)
[ ‹ К списку ]
```

The `tg_id` in the header is printed as digits with no thousands separators —
it is an identifier, not a quantity, and a grouped one is not even
searchable (it was grouped until 2026-09-13).

"🗑 Сброс X" asks for a one-tap confirmation before wiping (the same pattern
as disconnecting a platform in [ui_screens_users.md](ui_screens_users.md)):

```
<wipe every X achievement of this person and read them again from scratch?>
```
```
[ Да, сбросить ]   [ Отмена ]
```

## Chat list

```
💬 Чаты  (название · сколько человек публикуется)
```
```
[ <chat title> · N ]         (one row per chat)
[ <chat title> · N ]
[ ‹ Назад ]
```

Unlike the user list, this one is buttons only: a chat row is two facts wide,
and both of them fit on the button.

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
four 🗑 buttons was exactly what made them easy to mistap. Each of the three
bulk ones asks first, and the prompt says how many messages it is about to
take:

```
<delete N bot messages in «<chat>»? this cannot be undone>
```
```
[ Да, удалить ]   [ Отмена ]
```

### Chat card → pickers

Three settings are a value rather than a switch, so each opens its own
picker, with "•" marking what is set now and "‹ Назад" returning to the
section it came from:

```
Часовой пояс «<chat>»: UTC±N
```
```
[ UTC+2 ]  [ • UTC+3 ]  [ UTC+4 ]  [ UTC+5 ]
[ UTC+6 ]  [ UTC+7 ]  [ UTC+9 ]  [ UTC+10 ]
[ ✏️ Ввести вручную ]
[ ‹ Назад ]
```

```
Время итога дня в «<chat>»: HH:MM
```
```
[ 00 ]  [ 01 ]  [ 02 ]  [ 03 ]  [ 04 ]  [ 05 ]
[ 06 ]  [ 07 ]  [ 08 ]  [ 09 ]  [ 10 ]  [ 11 ]
[ 12 ]  [ 13 ]  [ 14 ]  [ 15 ]  [ 16 ]  [ 17 ]
[ 18 ]  [ 19 ]  [ • 20 ]  [ 21 ]  [ 22 ]  [ 23 ]
[ Часовой пояс ▸ ]
[ ‹ Назад ]
```

Whole hours only, and the timezone sits right there: "20:00" means nothing
until you know whose eight in the evening it is.

The rarity threshold is a free number, so it is a text input rather than a
grid — a chat can want 7.5%:

```
Порог «редкого» достижения в «<chat>»: N%
Пришли новое значение одним числом, например 12 или 7.5 — от 0 до 100.
Действует только на этот чат.
```
```
[ ‹ Назад ]
```

The anti-flood limit and window work the same way (a number each, their own
input), which is why the anti-flood section's own rows carry "▸".

**Language** is one shared value per chat, not per viewer — Telegram cannot
render a single group message differently for two people reading it, so
somebody has to decide for everyone. The super-admin today; a chat admin once
#47 exists.
