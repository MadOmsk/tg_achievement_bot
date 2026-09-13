# UI screens — user-facing (mockups, draft, issue #41)

Layout only, placeholders instead of real data — for editing. Nickname rules
and table contents are documented separately: see [tables.md](tables.md) for
"which rule builds `<nick>` here" (referenced below as **rule A/B/C/D/E**) and
for what actually goes into every `→ table:` line.

**Language convention** (2026-09-11): the prose here is English, like
everything else written in this project; the mockups stay in Russian, because
that is what the bot renders by default and therefore what you compare
against when testing. A person who switches their own language (#48) sees the
same layout with the `en` strings. Every Russian word in a mockup below is a
string from `bot/locales/ru/LC_MESSAGES/*.ftl` and nothing else — if a mockup
and the bot disagree on wording, the `.ftl` is what shipped.

**Platform order** (2026-09-13, owner decision): wherever platforms are
listed — a header, a keyboard, an admin block — the order is **Xbox,
PlayStation, Steam**, from `constants.platform_display_rank`. It is one
decision in one place because it had already drifted: /panel listed Steam
second, /stats listed PlayStation second, and both called themselves "a
fixed order".

**What is actually on screen** is captured separately, from a running build:
[captured_production.md](captured_production.md). A mockup here is the
decision; that file is the evidence. The two are compared by hand, not
generated from each other.

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
[ 🎮 Подключить PSN ]
[ 🎮 Подключить Steam ]
```

Timezone (right after the first login, when not set yet):

```
<timezone — the same screen /panel uses, see below>
```

## A published achievement / trophy

**This is a photo message, not a text one.** The achievement's own icon is
the photo and everything below is its *caption* — which is why the whole
card lives under Telegram's 1024-character caption cap, the same cap the
/hltb card has to respect. A text message would have no such limit; this
one does, and a card that exceeds it is not truncated by Telegram, it is
refused.

```
(photo: the achievement's icon, from the platform's own CDN)

🏆 <nick> получает достижение          ← rule B, the platform's own nick

<game> (<platform>) · <unlocked>/<total>
<badge> «<name>» · <gamerscore> G · редкость <rarity>%

<description, spoilered when secret>
```

Xbox 360 is the one exception to the photo: contract 1 gives a bare image
id with no documented way to turn it into a URL, so the card uses the
**game's own box art** instead of the achievement icon. Every Xbox 360
achievement in a game therefore carries the same picture.

The progress counter beside the game is #46. It is omitted when the total
is not known — a Steam game whose schema has not been cached yet, or a game
last polled before the bot stored totals at all. It is never guessed.

Platform names are the platform's own label (`🔵 PlayStation`, not "PSN";
`🟢 XBOX`; `⚫ Steam`), and the rarity carries the word "редкость" before
the number, both from the `.ftl`.

### PSN carries a second line

A PlayStation trophy list is split into groups: the base game plus one per
DLC. The trophy itself says which group it came from, so a single card says
which part of the game the person is progressing through, and how far:

```
🏆 <nick> получает трофей

Marvel's Spider-Man (🔵 PlayStation) · 31/74
CTNS: The Heist · 3/7
🥈 «<name>» · редкость 12.8%
```

A trophy from the base game names that group too, as "Основная игра" — Sony
names the default group after the game itself, and repeating the title
verbatim on two lines says nothing:

```
🏆 <nick> получает трофей

Marvel's Spider-Man (🔵 PlayStation) · 24/74
Основная игра · 24/51
🥉 «<name>» · редкость 31.4%
```

The trophy's own line never moves: the group line is inserted between the
game and the trophy, it does not replace anything.

No "DLC" prefix anywhere: a group is not always one. Spider-Man's group
`001` is called *New Game+*, which is a mode, not an add-on — so the group's
own name is printed and nothing is added to it. A game whose trophy list is
one single group (Ratchet & Clank, Stray) has no second line — it would only
repeat the first one.

Xbox and Steam have no notion of groups, so they stay at one line.

## A digest

**One form, two triggers** (2026-09-13, owner decision): a batch that
crosses the chat's own `digest_threshold`, and the backlog the anti-flood
filter releases once its window closes. Same layout, same rules — the only
difference is that the anti-flood one can genuinely mix platforms, so its
header uses the person's Telegram identity rather than one platform's
nickname.

**A digest is a gallery** (`sendMediaGroup`): every achievement's icon, in
order, with the caption on the first image. Duplicate image URLs are
dropped, so a batch of Xbox 360 achievements sharing one box art shows that
picture once rather than five times. The caption is under the same
1024-character cap as a single card, and a digest is the message most
likely to reach it.

```
(gallery: one icon per achievement, deduped by URL)

🏆 <nick> получает N достижений

<game> (<platform>) · <unlocked>/<total>
<badge> «<name>» · <gamerscore> G · редкость <rarity>%
<badge> «<name>» · <gamerscore> G · редкость <rarity>%

<game> (<platform>) · <unlocked>/<total>
<badge> «<name>» · редкость <rarity>%
```

One block per game, a blank line between blocks, every item listed — never
"и ещё N". The per-game counter is the same one a single card carries, and
it is on both triggers' digests.

**A digest never names a trophy group**, even when every trophy in a game's
block came from the same one (2026-09-13, owner decision). One block is one
*game*: its line carries the game's name and the game's own overall trophy
count. A group line would introduce a second subject into a message whose
whole job is grouping.

An all-PSN batch says "трофеев"; any mix says "достижений", because a
combined total across platforms is correctly "achievements".

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

Both toggles ("Профиль виден другим", "Язык") and the timezone cycle in
place: the panel redraws itself and the row's own label is the new state, so
there is no separate confirmation screen for either.

### /panel → Часовой пояс

```
🕐 Часовой пояс — по нему считаются «сегодня» и «за месяц».
```
```
[ UTC+2 ]  [ UTC+3 ]  [ UTC+4 ]  [ UTC+5 ]
[ UTC+6 ]  [ UTC+7 ]  [ UTC+9 ]  [ UTC+10 ]
[ Другой ▸ ]
[ ✏️ Ввести вручную ]
```

Eight offsets this community actually lives in, then an escape hatch.
"Другой ▸" opens the full −12…+14 grid (four per row) with the same
"✏️ Ввести вручную" below it; the manual option asks for one message
(`+3`, `-5`, `+5:30`) instead of paging a keyboard for a half-hour zone.

### /panel → 💬 Мои чаты

```
💬 Мои чаты
```
```
[ ✅ <chat title> ]          (one row per chat, ✅ = publishing there)
[ ✅ <chat title> ]
[ ‹ Назад ]
```

Every chat the person is known in, each row opening that chat's own card —
the list itself carries no text beyond the header, because the rows are the
content.

### /panel → one chat's card

```
💬 <chat title>
Публикация: ✅ включена / ⛔ выключена
```
```
[ Ачивки: любые / только редкие / скрыты ]   (tap cycles)
[ Сводка: N / никогда ▸ ]
[ Отписаться / Публиковать здесь ]
[ ‹ К списку чатов ]
```

Both settings are per person *and* per chat (`subscriptions`), which is the
whole reason this screen exists rather than one global pair in /panel.
"Ачивки" cycles in place like the panel's own toggles; "Сводка" opens a
picker, since it is a number:

```
Сводка вместо отдельных сообщений

Если за один раз в одной игре выбито столько достижений или больше —
в этот чат уйдёт одно сводное сообщение.
```
```
[ 2 ]  [ 3 ]  [ 4 ]  [ 5 ]
[ 6 ]  [ 8 ]  [ 10 ]  [ • никогда ]
[ ‹ Назад ]
```

The current value is marked with "•". "никогда" is stored as a number large
enough that no real session reaches it, so the publisher stays one
comparison.

Unsubscribing asks first, same one-tap shape as disconnecting a platform:

```
Перестать публиковать твои достижения в «<chat title>»?
```
```
[ Да, отписаться ]
[ Отмена ]
```

## /who

```
<whose stats do you want?>
```
```
[ <nick> ]  [ <nick> ]  [ <nick> ]     (three per row, rule P — the person)
[ <nick> ]  [ <nick> ]
[ Отмена ]
```

Everyone the chat has seen write, not only subscribers. A button opens that
person's /stats card in place. Names here are the person chain, never a bare
id (#40) — see **rule P** in [tables.md](tables.md).

## A private flow started in a group

`/connect_steam`, `/connect_psn`, `/connect_xbox` and `/panel` typed in a
group never answer there — the reply is one line and a button into the DM,
already at the right step:

```
<write to me privately — we'll connect X there>
```
```
[ Открыть ]→ссылка
```

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

## Reminder: the XBOX login has gone stale

Sent on its own, not in reply to anything — the only DM the bot initiates
besides the connect flow's own progress messages:

```
<sign in again — old achievements will not be posted, they are already
marked as seen>
```
```
[ Подключить XBOX ]→ссылка
```

The reassurance is the point: what makes people ignore a re-login prompt is
the fear of spamming the chat with a year of history.

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

When a leaderboard is capped by the global limit, one button appears under
it:

```
[ Показать всех ]
```

It replaces the message with the same block uncapped, in a plain (not
expandable) blockquote — the cap exists for the chat's scrollback, and asking
for everything is an explicit act.

## /delete_last

Deletes the chat's own latest non-system bot message and says what it was,
quoting the first two lines so the deletion is auditable rather than silent:

```
🗑 Удалил это сообщение:
"<first line of the deleted message>
<second line>"
```

The confirmation is itself a system message, so the message cleanup job takes
it away later.

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
