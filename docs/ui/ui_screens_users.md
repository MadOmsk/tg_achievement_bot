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

## Onboarding: /start

Greets, then offers every platform — one row each, same fixed order /panel
uses (#53). It used to lead with Xbox and hand over a Microsoft sign-in link,
leaving Steam and PSN to whoever already knew the commands.

Someone who already has *any* platform linked gets their panel instead, not
this screen.

```
<greeting — what the bot does, no single platform named>

<С чего начнём?>

[ Подключить XBOX ]        (a link out to Microsoft)
[ 🎮 Подключить Steam ]
[ 🎮 Подключить PSN ]
```

Timezone (right after the first login, when not set yet):

```
<timezone — the same screen /panel uses, see below>
```

## A published achievement / trophy

One per unlock, or one digest per batch — see CLAUDE.md's "Message formats"
for the grouping rules. The progress counter beside the game is #46.

```
🏆 <nick> получает достижение          ← rule B, the platform's own nick

<game> (<platform>) · <unlocked>/<total>
<badge> «<name>» · <gamerscore> · <rarity>%

<description, spoilered when secret>
```

The counter is omitted when the total is not known — a Steam game whose
schema has not been cached yet, or a game last polled before the bot stored
totals at all. It is never guessed.

**PSN carries a second line**, because a PlayStation trophy list is split
into groups: the base game plus one per DLC. The trophy itself says which
group it came from, so the message says which part of the game the person is
progressing through, and how far:

```
🏆 <nick> получает трофей

Marvel's Spider-Man (🔵 PSN) · 31/74
CTNS: The Heist · 3/7
🥈 «<name>» · 12.8%
```

A trophy from the base game names that group too, as "Основная игра" — Sony
names the default group after the game itself, and repeating the title
verbatim on two lines says nothing:

```
🏆 <nick> получает трофей

Marvel's Spider-Man (🔵 PSN) · 24/74
Основная игра · 24/51
🥉 «<name>» · 31.4%
```

The trophy's own line never moves: the group line is inserted between the
game and the trophy, it does not replace anything.

No "DLC" prefix anywhere: a group is not always one. Spider-Man's group
`001` is called *New Game+*, which is a mode, not an add-on — so the group's
own name is printed and nothing is added to it. A game whose trophy list is
one single group (Ratchet & Clank, Stray) has no second line — it would only
repeat the first one.

Xbox and Steam have no notion of groups, so they stay at one line.

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
