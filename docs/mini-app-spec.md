# Unlocked Mini App — functional specification

What the Mini App does, for whoever designs and builds its interface. It says
**what** a person can do and **which rules** hold, never how a screen looks: the
interface is being designed again from nothing (owner, 2026-10-26), and every
visual decision is that design's to make. The task for the design is
`docs/mini-app-design-brief.md`.

The previous interface was removed from `webapp/src`. It can be read in git
(`git show f49fa3b:webapp/src/…`) to check how a behaviour was handled — never
as a reference for how anything should look or be laid out.

## What must stay

- **The name is Unlocked**, written as one word; the logo and the wordmark
  (`webapp/public/logo.svg`, the icons, `public/fonts/nunito-800-wordmark.woff2`
  — the U as an open shackle) stay as they are.
- **The bottom navigation is glass**: a bar floating over the content, the
  content showing through it blurred.
- Everything else — the screens, how they lead into each other, the
  navigation's tabs, typography, colour, shapes, motion — is open.

## Audience and setting

- A small, non-commercial gaming community, 20–30 people, mostly
  Russian-speaking. Russian is the default language, English the other (per
  person: Settings → language). All copy lives in `webapp/src/i18n/locales/ru.ts`
  and `en.ts`; keys may be added, renamed or reworded with the design, and both
  files are kept complete.
- **Phone first.** The app runs in three places, with one code:
  1. **Inside Telegram** as a Mini App (the bot's menu button, a post's
     «Открыть» button, a DM link). Telegram signs every request (Init Data).
  2. **In a plain browser** — the same app; it signs in by itself (below).
  3. **Installed** from the browser as an app (a PWA, manifest and service
     worker in `webapp/public`), able to receive push notifications.
- What a person sees is about **themselves and the people they follow**. Chats
  exist (the bot posts to Telegram groups) but the app is not organised by chat.

## Core concepts

- **Person** — one member, known by a **nickname** (3–20 Latin letters/digits;
  a taken one gets four digits, `Name#1234`, always shown after it). A person is
  never shown by their Telegram name, username or a platform nickname; their
  nickname is their name everywhere. A person may have a custom avatar (else the
  Telegram photo, else initials).
- **Game account** — an Xbox, Steam or PSN account linked to a person (up to
  three PSN accounts). Each has its own nickname, avatar and posting switch.
- **Achievement** — earned on one game account in one achievement list. Has a
  name, description (in the reader's language when known), icon, rarity (% of
  players), gamerscore (Xbox) or a trophy tier (PSN: bronze, silver, gold,
  platinum), a date, and may be **secret** (its name and text hidden until the
  reader reveals it, unless the reader chose to always show secrets).
- **Achievement list** — one game's list of achievements on one platform;
  progress is "earned of total" (`40/50`).
- **Game** — one game across its platforms and versions (Xbox, PlayStation,
  Steam, PC stores), with its own name, years, studio, publisher, genres, story,
  pictures, HowLongToBeat hours and score, DLC, editions, series and related
  games (remaster, remake, collection). A game may have several achievement
  lists.
- **Follow** — one-way, no consent needed. Two people following each other are
  **friends**. A person can unfollow and **block** (a block removes the follows
  both ways and hides each from the other).
- **Presence** — whether a person is online, and which game they are playing,
  on which platform.
- **Favorite game** — a heart a person puts on a game.
- **News** — a game's developer posts (patches and news) from Steam.
- **Notification** — something the app tells a person (below).

## Privacy and naming rules (non-negotiable)

- **Who may see a person's activity** (achievements, games, progress, presence,
  favorites, follows lists) is their one privacy setting: everyone / friends /
  nobody — and "everyone" means **everyone who knows them**: shares an active
  chat with them or follows them. Oneself always. A block either way hides all.
  The server enforces it; a screen showing another person's activity shows what
  the server returns and handles "hidden" (a profile answers `hidden: true` with
  the nickname only).
- Nickname and avatar are not activity and are always visible.
- A Telegram id is never shown and never used to identify a person in the UI;
  people are keyed by `person_id`.
- Never print `@` before a name (a mention pings).
- Platform order in any list: **Xbox, PlayStation, Steam**.
- A game is never named by an id.

## Getting in

**Sign-in** (only outside Telegram; inside Telegram the person is already known):

- **Email**: type the address → a 6-digit code arrives → type it (the form can
  send itself on the sixth digit). A code lives 10 minutes, 5 guesses; resend
  after a minute (show a countdown). Errors come back as codes the app words:
  `invalid`, `too_soon`, `unavailable`, `send_failed`, `wrong_code`, `expired`,
  `taken`, `already`, `last_login`, `admin`, `in_telegram`, `not_linked`.
- **Passkey**: if the browser supports passkeys, the email start request says
  so (`passkey: true`); an address with keys is answered with key options
  instead of a mail, and the phone asks for the key. Refused or unavailable →
  ask again with `passkey: false` and the code is mailed. There is no separate
  "sign in with a key" control.
- **Telegram**: «Войти через Telegram» goes to Telegram's OAuth page in the same
  tab and comes back with `#tgAuthResult=` (the app posts it to
  `/auth/telegram`). The embeddable Login Widget is the fallback where no bot id
  is known.
- **Invites**: somebody new signs up in a browser only with an invite code
  (`XXXX-XXXX-XXXX-XXXX`). An unknown address's start, or a Telegram sign-in of
  somebody new, answers `invite_required` (with a `signup` token, 15 minutes):
  ask for the code, then `POST /auth/signup`. `?invite=CODE` in the link fills
  it and skips the step. `invite_invalid`, `signup_expired` are errors.
- `/auth/config` says which ways are available (`email`, `passkey`, `bot_id`,
  the bot's name).
- Sign-out ends the browser session.

**First run, after sign-in** (each shown once, in this order, when it applies):

1. **Choose a nickname** — `me.handle.confirmed` false: keep the suggested one
   or type another (`PUT /me/handle`, `POST /me/handle/confirm`). The first
   choice is free, later changes once a day (`too_soon`); case can change any
   time.
2. **Add an email** — `me.email_prompt` true: add one with the same code flow,
   or «Позже» (`POST /me/email/later`).
3. **Connect a game account** — a person with none should be led to connect one
   (the app is usable without, to follow friends).

**Merging two people**: when a signed-in person adds a login (email, Telegram)
that already belongs to another person and proves it, the answer carries a
`merge` preview (`GET /me/merge`): what each side has, and where both have
something (an Xbox, a Steam, Telegram, an email) the person picks which stays.
`POST /me/merge` does it, `DELETE` cancels.

## Game accounts

- **Connect Xbox**: `POST /connect/xbox` returns Microsoft's sign-in URL; the
  person signs in there and comes back. The history loads in the background.
- **Connect Steam**: by profile URL, vanity name or SteamID64
  (`POST /connect/steam`). The profile and its game details must be public —
  say how to open them when they are not.
- **Connect PSN**: by online id (`POST /connect/psn`); trophies must be visible
  to everyone. Up to three PSN accounts.
- **Unlink** each (`POST /disconnect/{platform}`), with a confirmation. History
  is kept; relinking finds it. Re-linking soon after a reset may be refused
  (cooldown) — say so.
- **Posting switch** per account (`PATCH /accounts/{platform}`): whether its
  achievements go to the person's chats.
- **Sync Xbox now** (`POST /sync`).
- An account's state comes in `/me`: linked, nickname, avatar, whether its
  achievements are visible to the bot (`achievements_visible` false → explain
  how to open them), a dead Xbox login (→ reconnect).

## Home — the person's own space

What it must offer (layout, order and emphasis are the design's):

- The person: avatar and nickname (opens their own card), presence.
- **Notifications** entry with the unread count (`me.notifications_unread`).
- **This month's activity**: the person's achievements this month (newest
  first) — a quick way into each achievement.
- **The people they follow**, with who is online / playing what now
  (`/club/online?scope=following`), friends first, then playing, online, the
  rest; a way to see all and to find people when there are none.
- **Favorite games** (`/game-favorites`), a tap opens the game.
- **Games played this month** with progress (earned/total) and how much was
  earned this month; past months selectable (`/club/people?person=me&month=YYYY-MM`,
  `months` lists the months with activity).
- With no game account: invite to connect one.

## Feed — achievements of the circle

- `/club/feed?scope=following&month=YYYY-MM`: the person's and their followed
  people's achievements, newest first, for one month; `months` lists months
  with posts.
- **Grouped by day**; inside a day, consecutive achievements of one person in
  one game form **one post**.
- A post shows: who (opens their profile), when, each achievement (name,
  description, icon, rarity, gamerscore or tier), the game (opens the game page)
  and the person's progress in it.
- A tap on an achievement opens **the achievement's page**.
- Secrets stay veiled until revealed (unless `show_secrets`).
- **Jump to a day** of the month (days with posts, and their counts) and **step
  to other months** (load the month stepped to).
- Build posts as the reader scrolls (a whole month at once is too much for a
  phone's browser).
- Pull to refresh.

## News — game news of the circle

- `/club/news?scope=following&month=YYYY-MM`: developer posts (patch / news) of
  the games the person and the people they follow played in the 60 days before
  the month's end, newest first, one per post. Untranslated.
- A post opens whole (`/club/news/post?appid=&gid=`): picture, game, date
  (with time), kind, title, the full text with its links, pictures and videos
  (rich text: `[label](url)`, a bare picture or video address on its own line —
  draw a picture, a video card), then «Открыть в Steam». Its game opens the game.

## Ranking

- `/club/summary?scope=following&month=YYYY-MM`: for the person and those they
  follow — counts for the last day, the month, the year; leaders by day / month /
  year; the games played; **«Охотятся вместе»** (achievements earned by several
  people, each once with everybody who earned it, the most shared first); rare
  finds. Each achievement opens its page; each person their profile.

## People and search

- **Search** (one place): games of our own catalog from two letters
  (`/game-search?q=`, never the internet) and people by nickname from three
  (`/people/search?q=`, a prefix or an exact `Name#1234`). A game opens its page,
  a person their card or profile.
- With no query: following, followers, **people you may know** (friends of
  friends, with how many shared — `/people/may-know`), people from shared chats
  (`/people/suggestions`).
- **Follow / unfollow / block / unblock** (`/people/{id}/follow|block`). A
  re-follow within ten minutes of an unfollow is refused (`too_soon`).
- **Follows lists**: following / friends / followers / blocked (`/me/following`,
  `/me/followers`, `/me/blocked`; somebody else's following / followers when
  privacy allows — `/people/{id}/following|followers`), searchable by nickname.
- **A person's card** (`/people/{id}`): nickname, avatar (zoomable), relation
  (follows you / friends), counts of following and followers (open the lists),
  their game accounts with nickname, level / gamerscore, counts, and links to
  their public profiles; follow / unfollow / block.
- **A person's profile** (`/club/people?person=`): like Home but theirs — their
  recent achievements, whom they follow, their favorite games, their games by
  month; the follow control. A hidden profile shows the nickname only.

## The game page

`GET /game?game_id=` or `?platform=&title_id=` (and `&person=` when opened from
somebody's achievement: their progress leads). One game whole:

- Pictures: a wide hero picture, a portrait box art (`art.hero`, `art.poster`,
  `art.header`); screenshots (open full screen, swipe through them).
- Name, years (`2015–2022`), developer and publisher (with "and others"),
  genres, the story (in the reader's language when there is one; long — expandable),
  the release day, platforms (each may link to its store page), HowLongToBeat
  score and age rating.
- **Progress**: the reader's (or the opened-from person's) count and total on
  their list, the last unlock; opens **the achievements**. The faces of the
  people they follow who played it, with their counts (each opens that person's
  achievements of this game).
- **News**: the newest developer posts (each opens whole), all of them.
- **HowLongToBeat hours**: main story, main + extras, 100%, link to HLTB.
- **DLC** (by release day; name, picture, year, hours), **editions** (shortest
  name first; name, cover), **each series the game is in** (newest game first,
  the current one marked; a game opens its page in place, back returns), **related
  games** (original / remaster / remake / VR / collection / part of a
  collection). Long lists: all of them a tap away, by year where they have years.
- **Favorite**: a heart (`PUT|DELETE /game/{id}/favorite`); the count of people
  who keep it (`favorites`).
- A game nobody played may have no achievement list — no progress then.

**The achievements of one list** (`GET /games/{platform}/{title_id}?person=`):

- Every achievement: name, description, icon, rarity, gamerscore or tier,
  earned or not and when; secrets veiled until revealed.
- Earned / still to earn (a toggle; earned newest first, the rest in the game's
  order); PSN groups (base game and each DLC) as sections when there are several.
- **Compare** with the person it was opened from: both people's marks per
  achievement.
- Score summary: gamerscore earned, or PSN tier counts.
- **Guides** (`/games/{platform}/{title_id}/guides`): per achievement a tip
  from the Steam community (`tips`, rich text) and YouTube guide videos
  (`videos`: title, channel, start time, part); the game's own guide video
  (`guide`). `complete: false` → ask again a little later (tips fill in).
- An achievement opens **its page**: its game (opens the game), rarity and points
  or tier, the picture (zoomable), when it was earned, name, description, then
  «Как получить»: the videos (open YouTube at the moment) and the tip whole.

**Small pictures**: an achievement picture smaller than the server's limit
(`me.picture`: `on`, `scale`, `low_res`) is not stretched to fill a block — it
is enlarged `scale` times relative to a 1024 px card and set in the middle on
a ground of its own. A game's cover never.

## Notifications

- **The list** (`GET /notifications`, the latest 200): each has `bold`, `lead`,
  `detail`, `image`, a time, read or not, what it is about (a person, a game, a
  news post). Grouped by day; unread stand out. A tap marks it read
  (`POST /notifications/read` with `ids`) and opens what it is about; «read all»
  without ids.
- **Kinds**: a new follower, a new friend, a new post (somebody followed earned
  achievements in a game), a game's news, a dead Xbox login.
- **Channels**: push (this device) and Telegram (needs Telegram linked). Each has
  an on/off switch and its own choice per kind (`PATCH /settings`:
  `notify_push`, `notify_telegram`, `notify_push_on`, `notify_telegram_on` as
  token lists): new posts — off / friends / everyone followed; new followers;
  new friends; game news — off / all / patches / news / favorites only; Xbox
  sign-in (push only). Nothing is on by default.
- **Push setup** (`webapp/src/core/push.ts`): `GET /push/key`,
  `POST|DELETE /push/subscription`. Say why a device cannot get pushes: inside
  Telegram (the bot's DMs are the notices there), an iPhone page not added to
  the Home Screen, a browser without push, push not set up on the server,
  blocked in the browser.
- Push and deep links open the app on the right thing (below).

## Settings

- **Profile**: nickname (rules above) and avatar (pick a picture, crop to a
  square, `PUT /me/avatar` — JPEG/PNG/WebP up to 2 MB; `DELETE` goes back to the
  Telegram photo); how others see the person.
- **Sign-in methods** (`GET /me/logins`): email — add or change with a code
  (`/me/email/start|verify`), never removed; Telegram — add (in a browser: the
  Login Widget or a `t.me/<bot>?start=link_<token>` link from
  `/me/telegram/link`), remove (`DELETE /me/telegram`, only from a browser, only
  while an email is left, never a super-admin); **passkeys** — list, add (named by
  the device), remove (`/me/passkeys…`), only in a browser on an https host.
- **Privacy**: who sees my activity (everyone / friends / nobody,
  `GET|PUT /me/privacy`) and the blocked people.
- **Game accounts**: connect, unlink, posting switch, sync, the notes above.
- **Posts in chats** (what of the person's goes to Telegram groups): the rarity
  mode — all / rare only / none (`rarity_mode`); a switch per chat
  (`/chats`, `PATCH /chats/{id}`); a switch per game account. A person without
  Telegram has no chats — offer to link Telegram.
- **Notifications** (above).
- **General**: language (ru / en), time zone (a UTC offset), always show secret
  achievements (`PATCH /settings`).
- **Invite a friend** (`/me/invites`): make codes, copy a code with its link
  (`?invite=`), see who came by each, delete an unused one.
- **Sign out**, **delete the account** (twice confirmed; `DELETE /me`).
- The super-admin's entries (below) for a super-admin only (`me.is_superadmin`).

## The super-admin's panel

Everything here is **drawn from what the server sends**; the app never keeps a
list of settings or actions of its own.

- **Home** (`/admin`): credential health (Xbox app, Steam key, PSN token,
  Anthropic, YouTube, mail), API load (per platform over 5 min / hour / day;
  Xbox per account median and busiest), sign-in emails against their caps, the
  octopus (catalog collector: on/off, queue, done, failures, last game), counts.
- **Keys** (`/admin/keys`): set / replace / clear each shared credential; a key
  is never shown back; errors from checking it are worded.
- **Settings** (`/admin/settings`, `PATCH`): groups of settings, each with its
  kind — number (with bounds), decimal, on/off, one of a list, an hour, a UTC
  offset (with a city where known) — label and hint; the server validates.
- **People** (`/admin/users`, `/admin/users/p<id>`): the list (with who has no
  game account), a person's card — their ways in, accounts with counts and
  diagnostics, chats, rarity mode — and their actions.
- **Chats** (`/admin/chats`, `/admin/chats/{id}/settings`): each chat's settings
  (on, language, time zone, daily summary and its hour, anti-flood) and actions.
- **Actions** (`GET|POST /admin/actions`): for a person, an account, a chat or
  the whole app — exclude / restore, refresh or reset an account, take a picture
  down, delete a person, the notification test, the promo, delete the last
  message, wipes. Each may need confirmations: the server answers step by step
  with the words to show and the label of «yes» until done.

## Moving around

- **Back** always steps back inside the app: the topmost open layer closes
  (Telegram's header BackButton inside Telegram, the phone's back in the browser
  and the installed app), and only at the root does the app close
  (`webapp/src/core/back-stack.ts`: one history entry per open layer, pushed
  when it opens; every layer with a way out registers).
- **A reload comes back where it was** (screen, person, game) for the tab's
  session; a link always wins; connecting an account starts over
  (`webapp/src/core/launch.ts`).
- **Deep links** (`webapp/src/core/launch.ts` parses them): `p=<person id>` a
  person; `u=<telegram id>` a person (old links); `g=<platform>:<title_id>` a
  game (with `p` — that person's progress); `n=<appid>:<gid>` a news post (with
  `g` — its game); `t=<tab>` a tab (feed, summary, news, people, settings);
  `c=<chat id>`; inside Telegram the same packed into the start parameter
  (`c<chat>[p|u<id>][t<tab>][g<base64url game>]`); `?invite=` an invite code.
  The bot's posts and pushes produce these; keep them working.
- **Pictures open full screen in the app** (zoom with two fingers, double-tap
  to zoom, a list swipes; never sent to an outside site).
- Everything that opens outside (stores, Steam, YouTube, HLTB) opens through
  Telegram's link opener inside Telegram, a new tab elsewhere.

## Data and API

- The client: `webapp/src/api` — one module per area with typed models
  (`*Models.ts`); the base adds Init Data inside Telegram and relies on the
  session cookie in a browser (`WEB_SESSION`).
- Everything is read from our own server; the app never calls a game platform.
- Endpoints, by area (all under `/api/mini`):
  - me & settings: `GET /me`, `PATCH /settings`, `PUT|DELETE /me/avatar`,
    `PUT /me/handle`, `POST /me/handle/confirm`, `GET|PUT /me/privacy`,
    `DELETE /me` (`POST /me/delete`), `GET /chats`, `PATCH /chats/{id}`,
    `PATCH /accounts/{platform}`;
  - sign-in: `GET /auth/config`, `POST /auth/email/start|verify`,
    `POST /auth/passkey/verify`, `POST /auth/telegram`, `POST /auth/signup`,
    `POST /auth/logout`;
  - logins: `GET /me/logins`, `POST /me/email/start|verify|later`,
    `POST|DELETE /me/telegram`, `GET /me/telegram/link`,
    `GET|POST|DELETE /me/merge`, `GET|POST /me/passkeys`,
    `POST /me/passkeys/options`, `DELETE /me/passkeys/{id}`;
  - invites: `GET|POST /me/invites`, `DELETE /me/invites/{code}`;
  - accounts: `POST /connect/{xbox|steam|psn}`, `POST /disconnect/{…}`,
    `POST /sync`;
  - circle: `GET /club/feed`, `/club/online`, `/club/people`, `/club/summary`,
    `/club/news`, `/club/news/post` (all with `scope=following`, `month=`);
  - people: `/people/search`, `/people/may-know`, `/people/suggestions`,
    `/people/{id}`, `/people/tg/{tg_id}`, `/people/{id}/following|followers`,
    `POST|DELETE /people/{id}/follow|block`, `/me/following`, `/me/followers`,
    `/me/blocked`;
  - games: `GET /game`, `GET /game-search`, `GET /game-favorites`,
    `PUT|DELETE /game/{id}/favorite`, `GET /games/{platform}/{title_id}`,
    `GET /games/{platform}/{title_id}/guides`;
  - pictures: `/avatar/p/{person_id}` (a face), `/ach-icon/…`, `/x360-icon/…`;
  - notifications: `GET /notifications`, `POST /notifications/read`,
    `GET /push/key`, `POST|DELETE /push/subscription`;
  - super-admin: `/admin`, `/admin/keys[/{name}]`, `/admin/settings`,
    `/admin/users[/{ref}]`, `/admin/chats[/{id}/settings]`, `/admin/actions`.

## What stays in code under the new interface

`webapp/src` keeps everything that is not interface:

- `api/` — the client and its models;
- `i18n/` — the copy in both languages and its helpers (`t`, `timeAgo`, …);
- `core/` — behaviour with no look of its own: `constants/` (platforms, rarity,
  routes, screen names, time zones), `launch.ts` (deep links, the place a
  reload returns to), `back-stack.ts`, `passkey.ts` (WebAuthn calls),
  `push.ts` (push subscription and why it is unavailable), `install.ts` (the
  browser's install prompt), `haptic.ts` (a tap of the phone, iPhone included),
  `game-open.tsx` (the contexts that open a game and an achievement),
  `home-cache.ts` (what Home showed last, drawn at once next time),
  `game-cache.ts`, `use-image-ratio.ts`, `telegram-login.tsx` (Telegram's Login
  Widget), `post-text.ts`, and the small helpers of the feed, the people and
  the games (`feed-utils.ts`, `people-utils.ts`, `game-utils.ts`);
- `main.tsx` — Telegram's init, the service worker, the install prompt;
- `App.tsx` — a bare shell to be replaced.
