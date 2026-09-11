# UI screens — user-facing (mockups, draft, issue #41)

Layout only, placeholders instead of real data — for editing. Nickname rules
and table contents are documented separately: see [tables.md](tables.md) for
"which rule builds `<nick>` here" (referenced below as **rule A/B/C/D/E**) and
for what actually goes into every `→ table:` line.

**Language convention** (2026-09-11): the prose here is English, like
everything else written in this project; the mockups stay in Russian, because
that is what the bot renders by default and therefore what you compare
against when testing. A person who switches their own language (#48) sees the
same layout with the `en` strings.

## Onboarding: /start, /connect_xbox

```
<greeting>

[ Войти через Microsoft ]
```

Timezone (right after the first login, when not set yet):

```
<timezone — the same screen /panel uses, see below>
```

## Disconnecting a platform: /disconnect_xbox, /disconnect_steam, /disconnect_psn

One pattern for all three — a one-tap confirmation, no separate text input:

```
<disconnect platform X? briefly, what will happen>

[ Да, отключить ]   [ Отмена ]
```

## Connecting Steam: /connect_steam

```
<how to send a profile link / vanity URL / SteamID64, plus the privacy link>
```

When the text looks like a profile but the bot is not sure — a confirmation:

```
<is this your profile? name, link>

[ Да, подключить ]   [ Нет ]
```

After a successful link — two separate messages, not one:

```
<connected: <nick>>
```
```
<backfill started>
```
(then, as its own message once the backfill finishes: `<backfill done, N
achievements>` — or, when the profile / game list is private, a message
pointing at Steam's privacy settings instead)

## Connecting PSN: /connect_psn

The same three-step pattern as Steam (link/id → connected → backfill), with
its own vocabulary ("trophies", never "achievements"). The list of private
games appears in the backfill-done message as its own line, and only when
there are any.

## /hltb

```
<game title?>

→ table: `hltb-recent-suggestions`   (only when the chat has recent games)

[ ❌ Отмена ]
```

Candidates after the search:

```
<pick your game>

→ table: `hltb-search-results`

[ ‹ ]  [ › ]
[ ❌ Отмена ]
```

The chosen game's card, sent as HLTB's own cover art with this as the
caption (it falls back to a plain text message when the game has no cover,
or Telegram refuses to fetch it):

```
⏱ <title> (<year>)

Основной сюжет · N ч
Основной + доп. · N ч
Полное прохождение · N ч

Платформы: <list>
Жанры: <genre>

▍<the game's own description, collapsed>

<link to HowLongToBeat>
```

The description is a collapsed blockquote, and the link stays the card's
last line — the numbers are what /hltb is for, the description is there for
whoever wants it and must not push the rest off a phone screen. Title,
platforms and genres are HLTB's own English strings and stay untranslated;
only the description is translated, once, and stored in both languages. A
game HLTB has no description for simply has no blockquote — no placeholder,
no empty line.

## Group hub (/help in a group, or the bot having just been added)

```
<short help for the chat's own commands>

<who already publishes here: a list of nicks, or "пока никто">
```

Buttons:
```
[ ✅ Публиковать мои достижения ]
[ 🔗 XBOX ]  [ 🎮 Steam ]  [ 🎮 PSN ]   (all three open a DM at the right step)
[ ⚙️ Настройки ]                        (opens a DM, /panel)
```

## /subscribe, /unsubscribe

```
<subscribed to / unsubscribed from publishing in this chat>
```

## /stats

```
📊 <Nick/Name>                                            [rule A]
🟢 XBOX: <nick>  ·  N достижений  ·  🏆 K  ·  gamerscore G    [rule B]
⚫ Steam: <nick>  ·  N достижений  ·  🏆 K                    [rule B]
🔵 PlayStation: <nick>  ·  N трофеев  ·  уровень L            [rule B]

Сегодня:   N достижений
За месяц:  N достижений (🟢 N · ⚫ N) (+G G)

→ table: `stats-recent-games`
```

## /panel

```
👤 <nick>                                                 [rule A]
🟢 XBOX: <nick>  ·  N достижений  ·  🏆 K  ·  gamerscore G    [rule B]
⚫ Steam: <nick>  ·  N достижений  ·  🏆 K                    [rule B]
🔵 PlayStation: <nick>  ·  N трофеев  ·  уровень L            [rule B]

Вход XBOX:   <token status>
Вход Steam:  <nick>  ·  <achievement visibility>              [rule B]
Вход PSN:    <nick>  ·  <trophy visibility>                   [rule B]
Публикация:  <chats>
Сейчас:      <online/offline, what they are playing>

Часовой пояс: UTC±N
```

Buttons:
```
[ Часовой пояс: UTC±N ▸ ]
[ 💬 Мои чаты ▸ ]
[ 🔄 Синхронизировать ]
[ Профиль виден другим: да/нет ▸ ]
[ Язык: Русский ▸ ]
[ 👤 Профиль | 🔕 Отключить XBOX ]   (or [ 🎮 Подключить Xbox ] when not connected)
[ 👤 Профиль | 🔕 Отключить Steam ]  (or [ 🎮 Подключить Steam ])
[ 👤 Профиль | 🔕 Отключить PSN ]    (or [ 🎮 Подключить PSN ])
[ Обновить ]
```

**Language** here is personal and applies to DMs only (#48) — a group follows
its own setting, which no individual member can move (see
[ui_screens_admin.md](ui_screens_admin.md)). One tap cycles it; the names are
always written in their own language ("Русский", "English") so somebody who
cannot read the current interface can still find theirs.

## /recent

```
🕘 Последние достижения

→ table: `recent-achievements`
```

## /online

```
🎮 Онлайн-статус игроков
Обновлено: HH:MM

→ table: `online-presence`
```

## /summary (day + month)

```
📊 Итог дня, <date>

24 часа: N достижений, +G G
→ table: `summary-leaderboard-day`

с 1 <month>: N достижений, +G G
→ table: `summary-leaderboard-month`

→ table: `summary-top-games-month`
```

In English the header puts the month before the day ("Daily summary, June
12"), and the month window reads "since June 1" — word order is each locale's
own business, decided in its `.ftl`, not by the caller.

## /summary_day

```
📊 Итог дня, <date>

24 часа: N достижений, +G G
→ table: `summary-leaderboard-day`
```

## /summary_month

```
📊 Итоги за месяц

с 1 <month>: N достижений, +G G
→ table: `summary-leaderboard-month`

→ table: `summary-top-games-month`
```
