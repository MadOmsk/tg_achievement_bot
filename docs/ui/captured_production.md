# The interface as the deployed bot renders it

Not a mockup and not a design decision — **a snapshot of what production
actually draws**, taken 2026-09-13 from commit `e51d044` (what is deployed)
and a read-only copy of the production database. The design decisions live
in [ui_screens_users.md](ui_screens_users.md),
[ui_screens_admin.md](ui_screens_admin.md) and [tables.md](tables.md); this
file exists so that there is something to check them against.

How it is taken: `scripts/ui_capture/` — the real Dispatcher, the real
routers and middleware, the real database, with only Telegram itself
replaced by a session that records each outgoing call instead of performing
it. So what is below is exactly what would have reached Telegram: the text
with its HTML, the inline keyboard row by row, and the URL of any photo or
gallery. No network: no platform API is touched, and the database is a copy,
never the server.

The prose here is English like everything else written in this project. Every
Russian (or English) word inside a fenced block came out of the bot's own
`.ftl` files — it is rendered output, not prose.

What it does not cover: a flow that continues by typing (a Steam nickname, an
Online ID, a manual timezone, a platform key) is captured at its prompt only,
not at the answer; a screen that needs a live platform call cannot be taken
at all and is marked as not building.

Three things to know about the snapshot itself:

- **The shared keys** (Steam/PSN/Anthropic) are re-encrypted with
  placeholders in the copy — the production `FERNET_KEY` is not on the
  development machine. On the key screens that shows as a masked placeholder
  value; alive/dead and the layout are real.
- Screens that change data (the language button, the toggles, subscribing)
  are rolled back between captures, because otherwise the next screen renders
  from data the capture itself wrote. The first run walked straight into
  that: half the inventory came out in English because the language button
  fired early, and a fabricated group callback with no chat title wrote NULL
  over the real one.
- **The main chat "XBOX CG" is set to English** (`chat_settings.locale =
  en`), so every group screen here is in English. That is the real state of
  the production database, not an artefact. The admin's own DMs are Russian.
  Where a message goes to both chats, it appears twice — once per locale.

---

## Personal screens

### /start

`start` · input: `/start` · command, private


```
👤 Igor
🟢 XBOX: Mad Omsk  ·  7 460 достижений  ·  🏆 9  ·  gamerscore 152 498
⚫ Steam: Mad Omsk  ·  1 678 достижений  ·  🏆 5
🔵 PlayStation: SuperOmsk  ·  17 трофеев  ·  уровень 5

Вход XBOX:   ✅ активен
Вход Steam:  Mad Omsk  ·  ✅ ачивки видны · 3 дн назад
Вход PSN:    SuperOmsk  ·  ✅ ачивки видны · 3 дн назад
Публикация:  ✅ в «XBOX CG», «test chat»
Сейчас:      не в сети (10 ч назад)

Часовой пояс: UTC+5
```

```
[ Часовой пояс: UTC+5 ▸ ]
[ 💬 Мои чаты ▸ ]
[ 🔄 Синхронизировать ]
[ Профиль виден другим: да ▸ ]
[ Язык: Русский ▸ ]
[ 👤 Профиль ]→url  [ 🔕 Отключить XBOX ]
[ 👤 Профиль ]→url  [ 🔕 Отключить Steam ]
[ 👤 Профиль ]→url  [ 🔕 Отключить PSN ]
[ Обновить ]
```

Plus a deletes a message

### /panel

`panel` · input: `/panel` · command, private


```
👤 Igor
🟢 XBOX: Mad Omsk  ·  7 460 достижений  ·  🏆 9  ·  gamerscore 152 498
⚫ Steam: Mad Omsk  ·  1 678 достижений  ·  🏆 5
🔵 PlayStation: SuperOmsk  ·  17 трофеев  ·  уровень 5

Вход XBOX:   ✅ активен
Вход Steam:  Mad Omsk  ·  ✅ ачивки видны · 3 дн назад
Вход PSN:    SuperOmsk  ·  ✅ ачивки видны · 3 дн назад
Публикация:  ✅ в «XBOX CG», «test chat»
Сейчас:      не в сети (10 ч назад)

Часовой пояс: UTC+5
```

```
[ Часовой пояс: UTC+5 ▸ ]
[ 💬 Мои чаты ▸ ]
[ 🔄 Синхронизировать ]
[ Профиль виден другим: да ▸ ]
[ Язык: Русский ▸ ]
[ 👤 Профиль ]→url  [ 🔕 Отключить XBOX ]
[ 👤 Профиль ]→url  [ 🔕 Отключить Steam ]
[ 👤 Профиль ]→url  [ 🔕 Отключить PSN ]
[ Обновить ]
```

Plus a deletes a message

### Panel: Refresh

`panel-refresh` · input: `panel:refresh` · button, private


```
👤 Igor
🟢 XBOX: Mad Omsk  ·  7 460 достижений  ·  🏆 9  ·  gamerscore 152 498
⚫ Steam: Mad Omsk  ·  1 678 достижений  ·  🏆 5
🔵 PlayStation: SuperOmsk  ·  17 трофеев  ·  уровень 5

Вход XBOX:   ✅ активен
Вход Steam:  Mad Omsk  ·  ✅ ачивки видны · 3 дн назад
Вход PSN:    SuperOmsk  ·  ✅ ачивки видны · 3 дн назад
Публикация:  ✅ в «XBOX CG», «test chat»
Сейчас:      не в сети (10 ч назад)

Часовой пояс: UTC+5
```

```
[ Часовой пояс: UTC+5 ▸ ]
[ 💬 Мои чаты ▸ ]
[ 🔄 Синхронизировать ]
[ Профиль виден другим: да ▸ ]
[ Язык: Русский ▸ ]
[ 👤 Профиль ]→url  [ 🔕 Отключить XBOX ]
[ 👤 Профиль ]→url  [ 🔕 Отключить Steam ]
[ 👤 Профиль ]→url  [ 🔕 Отключить PSN ]
[ Обновить ]
```

Plus a toast — «Обновил»

### Panel: timezone picker

`panel-tz` · input: `panel:tz` · button, private


```
🕐 Часовой пояс — по нему считаются «сегодня» и «за месяц».
```

```
[ UTC+2 ]  [ UTC+3 ]  [ UTC+4 ]  [ UTC+5 ]
[ UTC+6 ]  [ UTC+7 ]  [ UTC+9 ]  [ UTC+10 ]
[ Другой ▸ ]
[ ✏️ Ввести вручную ]
```

### Panel: my chats

`panel-chatlist` · input: `panel:chatlist` · button, private


```
💬 Мои чаты
```

```
[ ✅ XBOX CG ]
[ ✅ test chat ]
[ ‹ Назад ]
```

### Panel: one chat's card

`panel-chat` · input: `panel:chat:-1001103247578` · button, private


```
💬 XBOX CG

Публикация: ✅ включена
```

```
[ Ачивки: любые ]
[ Сводка: никогда ▸ ]
[ Отписаться ]
[ ‹ К списку чатов ]
```

### Panel: rarity mode in a chat

`panel-chatrarity` · input: `panel:chatrarity:-1001103247578` · button, private


```
💬 XBOX CG

Публикация: ✅ включена
```

```
[ Ачивки: только редкие ]
[ Сводка: никогда ▸ ]
[ Отписаться ]
[ ‹ К списку чатов ]
```

### Panel: digest threshold

`panel-chatdigest` · input: `panel:chatdigest:-1001103247578` · button, private


```
Сводка вместо отдельных сообщений

Если за один раз в одной игре выбито столько достижений или больше — в этот чат уйдёт одно сводное сообщение.
```

```
[ 2 ]  [ 3 ]  [ 4 ]  [ 5 ]
[ 6 ]  [ 8 ]  [ 10 ]  [ • никогда ]
[ ‹ Назад ]
```

### Panel: unsubscribe from a chat (confirmation)

`panel-chatunsub` · input: `panel:chatunsub:-1001103247578` · button, private


```
Перестать публиковать твои достижения в «XBOX CG»?
```

```
[ Да, отписаться ]
[ Отмена ]
```

### Panel: profile visible to others

`panel-linkstoggle` · input: `panel:linkstoggle` · button, private


```
👤 Igor
🟢 XBOX: Mad Omsk  ·  7 460 достижений  ·  🏆 9  ·  gamerscore 152 498
⚫ Steam: Mad Omsk  ·  1 678 достижений  ·  🏆 5
🔵 PlayStation: SuperOmsk  ·  17 трофеев  ·  уровень 5

Вход XBOX:   ✅ активен
Вход Steam:  Mad Omsk  ·  ✅ ачивки видны · 3 дн назад
Вход PSN:    SuperOmsk  ·  ✅ ачивки видны · 3 дн назад
Публикация:  ✅ в «XBOX CG», «test chat»
Сейчас:      не в сети (10 ч назад)

Часовой пояс: UTC+5
```

```
[ Часовой пояс: UTC+5 ▸ ]
[ 💬 Мои чаты ▸ ]
[ 🔄 Синхронизировать ]
[ Профиль виден другим: нет ▸ ]
[ Язык: Русский ▸ ]
[ 👤 Профиль ]→url  [ 🔕 Отключить XBOX ]
[ 👤 Профиль ]→url  [ 🔕 Отключить Steam ]
[ 👤 Профиль ]→url  [ 🔕 Отключить PSN ]
[ Обновить ]
```

Plus a toast — «Скрыл»

### Panel: language

`panel-locale` · input: `panel:locale` · button, private


```
👤 Igor
🟢 XBOX: Mad Omsk  ·  7 460 achievements  ·  🏆 9  ·  gamerscore 152 498
⚫ Steam: Mad Omsk  ·  1 678 achievements  ·  🏆 5
🔵 PlayStation: SuperOmsk  ·  17 trophies  ·  level 5

XBOX login:   ✅ active
Steam login:  Mad Omsk  ·  ✅ achievements visible · 3 d ago
PSN login:    SuperOmsk  ·  ✅ achievements visible · 3 d ago
Publishing:   ✅ in «XBOX CG», «test chat»
Now:          offline (10 h ago)

Timezone:     UTC+5
```

```
[ Timezone: UTC+5 ▸ ]
[ 💬 My chats ▸ ]
[ 🔄 Sync now ]
[ Profile visible to others: yes ▸ ]
[ Language: English ▸ ]
[ 👤 Profile ]→url  [ 🔕 Disconnect XBOX ]
[ 👤 Profile ]→url  [ 🔕 Disconnect Steam ]
[ 👤 Profile ]→url  [ 🔕 Disconnect PSN ]
[ Refresh ]
```

Plus a toast — «English»

### Panel: disconnect Xbox (confirmation)

`panel-disconnect` · input: `panel:disconnect` · button, private


```
Отключить XBOX?

Удалю токен и подписки. Историю достижений оставлю — она нужна статистике чата, и при повторном входе старые достижения не хлынут в чат заново.

Само разрешение остаётся в аккаунте Microsoft — убрать его можно только самому: https://account.live.com/consent/Manage
```

```
[ Да, отключить ]
[ Отмена ]
```

### /connect_xbox

`connect-xbox` · input: `/connect_xbox` · command, private


```
XBOX уже подключён. Если нужно войти заново — сначала /disconnect_xbox.
```

### /disconnect_xbox

`disconnect-xbox` · input: `/disconnect_xbox` · command, private


```
Отключить XBOX?

Удалю токен и подписки. Историю достижений оставлю — она нужна статистике чата, и при повторном входе старые достижения не хлынут в чат заново.

Само разрешение остаётся в аккаунте Microsoft — убрать его можно только самому: https://account.live.com/consent/Manage
```

```
[ Да, отключить ]
[ Отмена ]
```

### Disconnecting Xbox: cancelled

`disconnect-xbox-no` · input: `disconnect:no` · button, private

Draws nothing — only deletes a message, toast.

### «Sign in again» button

`relogin` · input: `relogin` · button, private


```
Войди заново — старые достижения в чат не полетят, они уже отмечены как виденные.
```

```
[ Подключить XBOX ]→url
```

### Timezone: more

`tz-more` · input: `tz:more` · button, private


```
🕐 Твой часовой пояс?
```

```
[ UTC−12 ]  [ UTC−11 ]  [ UTC−10 ]  [ UTC−9 ]
[ UTC−8 ]  [ UTC−7 ]  [ UTC−6 ]  [ UTC−5 ]
[ UTC−4 ]  [ UTC−3 ]  [ UTC−2 ]  [ UTC−1 ]
[ UTC+0 ]  [ UTC+1 ]  [ UTC+2 ]  [ UTC+3 ]
[ UTC+4 ]  [ UTC+5 ]  [ UTC+6 ]  [ UTC+7 ]
[ UTC+8 ]  [ UTC+9 ]  [ UTC+10 ]  [ UTC+11 ]
[ UTC+12 ]  [ UTC+13 ]  [ UTC+14 ]
[ ✏️ Ввести вручную ]
[ Пропустить ]
```

### Timezone: type it in

`tz-manual` · input: `tz:manual` · button, private


```
Пришли смещение одним сообщением, со знаком: например +3, -5 или +5:30.
```

### /connect_steam

`connect-steam` · input: `/connect_steam` · command, private


```
Steam уже подключён: Mad Omsk.
```

### /disconnect_steam

`disconnect-steam` · input: `/disconnect_steam` · command, private


```
Отключить Steam (Mad Omsk)?
```

```
[ Да, отключить ]
[ Отмена ]
```

### Disconnecting Steam: cancelled

`steam-disconnect-no` · input: `steam:disconnect:no` · button, private

Draws nothing — only deletes a message, toast.

### /connect_psn

`connect-psn` · input: `/connect_psn` · command, private


```
PSN уже подключён: SuperOmsk.
```

### /disconnect_psn

`disconnect-psn` · input: `/disconnect_psn` · command, private


```
Отключить PSN (SuperOmsk)?
```

```
[ Да, отключить ]
[ Отмена ]
```

### Disconnecting PSN: cancelled

`psn-disconnect-no` · input: `psn:disconnect:no` · button, private

Draws nothing — only deletes a message, toast.

### /hltb in a DM

`hltb-dm` · input: `/hltb` · command, private


```
Название игры? Точное не нужно — покажу варианты.
Ответь на это сообщение (реплаем).
```

```
[ ❌ Отмена ]
```

### /hltb: cancelled

`hltb-cancel` · input: `hltb:cancel` · button, private

Draws nothing — only toast, deletes a message.

## Super-admin panel

### /admin — home

`admin` · input: `/admin` · command, private


```
⚙️ Администрирование  ·  обновлено 00:18

Пользователей: 7 (исключено: 0)
  XBOX:  5 (вход активен: 5, без входа: 0)
  Steam: 2
  PSN:   4
Чатов:          2
API XBOX (достижения):  0/100 за 15с · 0/300 за 5 мин
API Steam (достижения): 0/100 000 за 1440 мин
Ключ Steam: ✅ жив, проверен 10 ч назад
Ключ PSN:   ✅ жив, проверен 11 ч назад
Запросов к PSN за сутки: 0
```

```
[ 👤 Новые пользователи ▸ ]
[ ⚙️ Глобальные настройки ▸ ]
[ Пользователи ▸ ]
[ Чаты ▸ ]
[ 🔑 Ключи платформ ▸ ]
```

Plus a deletes a message

### Admin: home

`admin-home` · input: `a:home` · button, private


```
⚙️ Администрирование  ·  обновлено 00:18

Пользователей: 7 (исключено: 0)
  XBOX:  5 (вход активен: 5, без входа: 0)
  Steam: 2
  PSN:   4
Чатов:          2
API XBOX (достижения):  0/100 за 15с · 0/300 за 5 мин
API Steam (достижения): 0/100 000 за 1440 мин
Ключ Steam: ✅ жив, проверен 10 ч назад
Ключ PSN:   ✅ жив, проверен 11 ч назад
Запросов к PSN за сутки: 0
```

```
[ 👤 Новые пользователи ▸ ]
[ ⚙️ Глобальные настройки ▸ ]
[ Пользователи ▸ ]
[ Чаты ▸ ]
[ 🔑 Ключи платформ ▸ ]
```

### Admin: platform keys

`admin-keys` · input: `a:keys` · button, private


```
🔑 Ключи платформ

Steam: ✅ настроен
PSN: ✅ настроен
Anthropic: ✅ настроен
```

```
[ Сменить ключ Steam ]
[ Убрать ключ Steam ]
[ Сменить NPSSO (PSN) ]
[ Убрать NPSSO (PSN) ]
[ Сменить ключ Anthropic ]
[ Убрать ключ Anthropic ]
[ ‹ Назад ]
```

### Admin: entering the Steam key

`admin-keyset` · input: `a:keyset:steam` · button, private


```
Пришли Steam Web API key одним сообщением — получить его:
https://steamcommunity.com/dev/apikey
```

```
[ Отмена ]
```

### Admin: defaults for new users

`admin-newusers` · input: `a:newusers` · button, private


```
👤 Новые пользователи — настройки по умолчанию

Действует только на подписки, оформленные с этого момента — уже существующие
не трогает.
```

```
[ Ачивки по умолчанию: только редкие ▸ ]
[ Профиль виден другим: нет ▸ ]
[ ‹ Назад ]
```

### Admin: display limits

`admin-limits` · input: `a:limits` · button, private


```
⚙️ Глобальные настройки

Списки /summary и /stats можно сделать безлимитными (0) — они и так лежат
в сворачиваемой цитате, урезать нечего.
```

```
[ Строк в /summary: без ограничения ▸ ]
[ Игр в /stats: без ограничения ▸ ]
[ Результатов поиска и подсказок HLTB: 25 ▸ ]
[ Результатов на странице (HLTB): 5 ▸ ]
[ Автоудаление системных сообщений (мин): 5 ▸ ]
[ Интервал автообновления /online (мин): 5 ▸ ]
[ Автообновление /online, часов: 3 ▸ ]
[ Проверка ключей / автообновление /admin (мин): 30 ▸ ]
[ ‹ Назад ]
```

### Admin: user list

`admin-users` · input: `a:users:0` · button, private


```
👥 Пользователи  (1/1)

🟢✅⚫ Ｗｈａｌｅｒｉｄｅｒ➑➍ · 10 ч назад · 0 / 0
🟢✅ Key Real · 10 ч назад · 5 / 56
🔵 Igor · 15 ч назад · 4 / 4
🔵 k_maks · 23 ч назад · 0 / 29
🟢✅ Александр · 1 дн назад · 0 / 0
🟢✅🔵 Vitaliy · 1 дн назад · 0 / 32
🟢✅⚫🔵 Igor · 2 дн назад · 0 / 5

Колонки: когда был в сети · достижений сегодня / за месяц
```

```
[ 🟢✅⚫ Ｗｈａｌｅｒｉｄｅｒ➑➍ ]
[ 🟢✅ Key Real ]
[ 🔵 Igor ]
[ 🔵 k_maks ]
[ 🟢✅ Александр ]
[ 🟢✅🔵 Vitaliy ]
[ 🟢✅⚫🔵 Igor ]
[ ‹ Назад ]
```

### Admin: user card (PSN only)

`admin-user` · input: `a:u:319472587` · button, private


```
👤 k_maks, @keimaks, tg_id 319 472 587

🔵 PSN: kmaks90
account_id 2137511672114883405
Вход: ✅ ачивки видны · 3 дн назад
251 трофей  ·  сегодня 0  ·  уровень 76
В сети: 10 ч назад

Подписан: «XBOX CG»
```

```
[ 🚫 Исключить из системы ]
[ 🔄 Обновить PSN ]  [ 🗑 Сброс PSN ]
[ ‹ К списку ]
```

### Admin: user card (Xbox + Steam)

`admin-user-xbox` · input: `a:u:127383366` · button, private


```
👤 Ｗｈａｌｅｒｉｄｅｒ➑➍, @whalerider84, tg_id 127 383 366

🟢 XBOX: Whalerider84
XUID 2535446000925749
Вход: ✅ активен, обновлён 10 ч назад
4 224 достижения  ·  сегодня 0  ·  gamerscore 100 030
В сети: 10 ч назад, Microsoft Flight Simulator 2024

⚫ Steam: Whalerider84
id 76561199705430962
Вход: ⚠️ ачивки скрыты · 3 дн назад
0 достижений  ·  сегодня 0
В сети: 10 ч назад

Подписан: «XBOX CG»
```

```
[ 🚫 Исключить из системы ]
[ 🔄 Обновить XBOX ]  [ 🗑 Сброс XBOX ]
[ 🔄 Обновить Steam ]  [ 🗑 Сброс Steam ]
[ ‹ К списку ]
```

### Admin: chat list

`admin-chats` · input: `a:chats` · button, private


```
💬 Чаты  (название · сколько человек публикуется)
```

```
[ XBOX CG · 5 ]
[ test chat · 2 ]
[ ‹ Назад ]
```

### Admin: chat card

`admin-chat` · input: `a:chat:-1001103247578` · button, private


```
💬 XBOX CG

Состояние:    активен
Публикуется:  5 чел.
Порог редк.:  15%
Итог дня:     да, в 20:00
Часовой пояс: UTC+3
Мин. G:       0
Антиспам:     3 ач. / 60 мин
Язык:         English

Подписаны: Igor, k_maks, Key Real, Vitaliy, Ｗｈａｌｅｒｉｄｅｒ➑➍
```

```
[ Порог редкости: 15% ▸ ]
[ Итог дня: включён ▸ ]
[ Антиспам: 3 ач. / 60 мин ▸ ]
[ Язык: English ]
[ ⏸ Отключить чат ]
[ 🗑 Сообщения ▸ ]
[ ‹ К списку ]
```

### Admin: chat → daily summary

`admin-chat-summary` · input: `a:msum:-1001103247578` · button, private


```
💬 XBOX CG

Состояние:    активен
Публикуется:  5 чел.
Порог редк.:  15%
Итог дня:     да, в 20:00
Часовой пояс: UTC+3
Мин. G:       0
Антиспам:     3 ач. / 60 мин
Язык:         English

Подписаны: Igor, k_maks, Key Real, Vitaliy, Ｗｈａｌｅｒｉｄｅｒ➑➍
```

```
[ Итог дня: включён ]
[ Время итога: 20:00 (UTC+3) ▸ ]
[ ‹ Назад ]
```

### Admin: chat → anti-flood

`admin-chat-flood` · input: `a:mflood:-1001103247578` · button, private


```
💬 XBOX CG

Состояние:    активен
Публикуется:  5 чел.
Порог редк.:  15%
Итог дня:     да, в 20:00
Часовой пояс: UTC+3
Мин. G:       0
Антиспам:     3 ач. / 60 мин
Язык:         English

Подписаны: Igor, k_maks, Key Real, Vitaliy, Ｗｈａｌｅｒｉｄｅｒ➑➍
```

```
[ Антиспам-фильтр: включён ]
[ Антиспам: 3 ач. ▸ ]  [ Окно антиспама: 60 мин ▸ ]
[ ‹ Назад ]
```

### Admin: chat → message cleanup

`admin-chat-cleanup` · input: `a:mdel:-1001103247578` · button, private


```
💬 XBOX CG

Состояние:    активен
Публикуется:  5 чел.
Порог редк.:  15%
Итог дня:     да, в 20:00
Часовой пояс: UTC+3
Мин. G:       0
Антиспам:     3 ач. / 60 мин
Язык:         English

Подписаны: Igor, k_maks, Key Real, Vitaliy, Ｗｈａｌｅｒｉｄｅｒ➑➍
```

```
[ 🗑 Последнее ]
[ 🗑 Бота (24ч) ]
[ 🗑 Системные (24ч) ]
[ 🗑 Все системные ]
[ ‹ Назад ]
```

### Admin: chat → timezone

`admin-chat-tz` · input: `a:ctz:-1001103247578` · button, private


```
Часовой пояс «XBOX CG»: UTC+3
```

```
[ UTC+2 ]  [ • UTC+3 ]  [ UTC+4 ]  [ UTC+5 ]
[ UTC+6 ]  [ UTC+7 ]  [ UTC+9 ]  [ UTC+10 ]
[ ✏️ Ввести вручную ]
[ ‹ Назад ]
```

### Admin: chat → summary time

`admin-chat-time` · input: `a:ctime:-1001103247578` · button, private


```
Время итога дня в «XBOX CG»: 20:00
```

```
[ 00 ]  [ 01 ]  [ 02 ]  [ 03 ]  [ 04 ]  [ 05 ]
[ 06 ]  [ 07 ]  [ 08 ]  [ 09 ]  [ 10 ]  [ 11 ]
[ 12 ]  [ 13 ]  [ 14 ]  [ 15 ]  [ 16 ]  [ 17 ]
[ 18 ]  [ 19 ]  [ • 20 ]  [ 21 ]  [ 22 ]  [ 23 ]
[ Часовой пояс ▸ ]
[ ‹ Назад ]
```

### Admin: chat → wipe messages (confirmation)

`admin-chat-wipe` · input: `a:cwipe:-1001103247578` · button, private


```
Стереть 8 сообщений бота в «XBOX CG» за последние 24 часа?

Необратимо. Считаются только сообщения, отправленные с тех пор, как завели
этот учёт, — более старые бот не помнит.
```

```
[ Да, стереть ]
[ Отмена ]
```

### Admin: reset a platform (confirmation)

`admin-reset` · input: `a:reset:psn:319472587` · button, private

> ⚠️ **This screen does not build:** `TypeError: 'str' object is not callable`

## Group screens

### /help in a group

`group-help` · input: `/help` · command, supergroup


```
🎮 I watch the achievements of everyone playing on XBOX and Steam and post them here — with a rarity filter, personal stats, and a daily summary.

Chat commands:
/stats [@who] — stats: yours with no argument, someone else's with a name
/who — look up a specific player's stats
/online — who's in a game right now
/recent [N] — the chat's latest achievements
/summary — the day and the month in review
/hltb — a game's HowLongToBeat summary

Settings are in a DM, /panel.

Publishing: Igor, k_maks, Key Real, Vitaliy, Ｗｈａｌｅｒｉｄｅｒ➑➍
```

```
[ ✅ Publish my achievements ]
[ 🔗 XBOX ]→url  [ 🎮 Steam ]→url  [ 🎮 PSN ]→url
[ ⚙️ Settings ]→url
```

Plus a GetMe

### /subscribe

`group-subscribe` · input: `/subscribe` · command, supergroup


```
You're already publishing here.
```

### /unsubscribe

`group-unsubscribe` · input: `/unsubscribe` · command, supergroup


```
Stop publishing your achievements in this chat?
```

```
[ Yes, unsubscribe ]
[ Cancel ]
```

### /stats

`group-stats` · input: `/stats` · command, supergroup


```
📊 <b>Igor</b>
🟢 XBOX: <a href="https://account.xbox.com/en-us/profile?gamertag=Mad%20Omsk">Mad Omsk</a>  ·  7 460 achievements  ·  🏆 9  ·  gamerscore 152 498
🔵 PlayStation: <a href="https://my.playstation.com/profile/SuperOmsk">SuperOmsk</a>  ·  17 trophies  ·  level 5
⚫ Steam: <a href="https://steamcommunity.com/profiles/76561197981065056">Mad Omsk</a>  ·  1 678 achievements  ·  🏆 5

Today:      0 achievements
This month: 5 achievements (🟢 1 · ⚫ 4) (+10 G)

<b>Games in the last 30 days</b>
<blockquote expandable>1. 🟢 Dispatch — 13 ach. (+360 G)
2. 🟢 Denshattack! — 4 ach. (+40 G)
3. 🟢 Wobbly Life — 2 ach. (+40 G)
4. 🟢 Gears of War 3 — 1 ach. (+15 G)
5. 🟢 Minecraft — 1 ach. (+10 G)
6. 🟢 Gears of War: Reloaded — 1 ach. (+10 G)
7. 🟢 Microsoft Solitaire Collection — 1 ach. (+10 G)
8. ⚫ G.O.P.O.T.A — 3 ach.
9. 🔵 Ratchet &amp; Clank™ — 2 ach.
10. ⚫ Weird West: Definitive Edition — 1 ach.
11. ⚫ HELLDIVERS™ 2 — 1 ach.</blockquote>
```

Plus a deletes a message

### /stats @somebody

`group-stats-other` · input: `/stats @keimaks` · command, supergroup


```
📊 <b>k_maks</b>
🔵 PlayStation: <a href="https://my.playstation.com/profile/kmaks90">kmaks90</a>  ·  251 trophies  ·  level 76

Today:      0 achievements
This month: 29 achievements

<b>Games in the last 30 days</b>
<blockquote expandable>1. 🔵 Marvel&#x27;s Spider-Man Remastered — 26 ach.
2. 🔵 Returnal — 4 ach.
3. 🔵 STAR WARS Jedi: Fallen Order — 4 ach.
4. 🔵 ASTRO’s PLAYROOM — 1 ach.
5. 🔵 Hogwarts Legacy — 1 ach.</blockquote>
```

Plus a deletes a message

### /online

`group-online` · input: `/online` · command, supergroup


```
🎮 <b>Who's online</b>
<i>Updated: 00:18</i>

🟢 Whalerider84 — playing — Microsoft Flight Simulator 2024
🟢 RideTheSun — online, not playing
⚪ Vitaliy — offline
⚪ k_maks — offline
⚪ Igor — offline
⚪ Александр — offline
```

### /who

`group-who` · input: `/who` · command, supergroup


```
Whose stats do you want?
```

```
[ Ｗｈａｌｅｒｉｄｅｒ➑➍ ]  [ Key Real ]  [ Vitaliy ]
[ k_maks ]  [ Igor ]  [ Александр ]
[ Cancel ]
```

### /recent

`group-recent` · input: `/recent` · command, supergroup


```
🕘 <b>Latest achievements</b>
<blockquote expandable>💎 Key Real — 🟢 Call of Duty®: Black Ops Co…, Keep Your Friends Close (+15 G · 7.55%) · 11 h ago
🏆 Key Real — 🟢 Call of Duty®: Black Ops Co…, Fracture Jaw (+15 G · 27.81%) · 11 h ago
💎 Key Real — 🟢 Call of Duty®: Black Ops Co…, Scorched Earth (+15 G · 1.51%) · 11 h ago
🏆 Key Real — 🟢 Call of Duty®: Black Ops Co…, Jack of All Trades (+15 G · 16.38%) · 12 h ago
🏆 Key Real — 🟢 Call of Duty®: Black Ops Co…, Nowhere Left to Run (+15 G · 35.61%) · 12 h ago</blockquote>
```

Plus a deletes a message

### /summary

`group-summary` · input: `/summary` · command, supergroup


```
📊 <b>Daily summary</b>, September 13

<b>24 hours:</b> 5 achievements, +75 G
<blockquote expandable>1. Key Real — 5 achievements (🟢 5) (+75 G)
2. Ｗｈａｌｅｒｉｄｅｒ➑➍ — 0 achievements (+0 G)
3. Igor — 0 achievements (+0 G)
4. Vitaliy — 0 achievements (+0 G)
5. k_maks — 0 achievements (+0 G)</blockquote>

<b>since September 1:</b> 122 achievements, +1 900 G
<blockquote expandable>1. Key Real — 56 achievements 💎32 (🟢 56) (+1 670 G)
2. Vitaliy — 32 achievements 💎26 (🟢 5 · 🔵 27) (+220 G)
3. k_maks — 29 achievements (🔵 29) (+0 G)
4. Igor — 5 achievements (🟢 1 · ⚫ 4) (+10 G)
5. Ｗｈａｌｅｒｉｄｅｒ➑➍ — 0 achievements (+0 G)</blockquote>

<b>Games this month</b>
<blockquote expandable>1. 🔵 Call of Duty®: Black Ops II — 27 trophies 🥇1 🥈2 🥉24
2. 🔵 Marvel&#x27;s Spider-Man Remastered — 26 trophies 🥈4 🥉22
3. 🟢 S.T.A.L.K.E.R. 2: Heart of Chornobyl - Windows Edition — 16 achievements (+340 G)
4. 🟢 Rue Valley — 16 achievements (+715 G)
5. 🟢 Breathedge — 15 achievements (+310 G)
6. 🟢 Call of Duty®: Black Ops Cold War (Windows) — 5 achievements (+75 G)
7. 🟢 Denshattack! — 4 achievements (+120 G)
8. ⚫ G.O.P.O.T.A — 3 achievements
9. 🔵 STAR WARS Jedi: Fallen Order — 3 trophies 🥉3
10. 🟢 Resonance: A Plague Tale Legacy — 2 achievements (+30 G)
11. ⚫ Weird West: Definitive Edition — 1 achievement
12. 🟢 Idle Wizard (Xbox One) — 1 achievement (+100 G)
13. 🟢 DPS IDLE 2 — 1 achievement (+100 G)
14. 🟢 VALORANT — 1 achievement (+100 G)
15. 🟢 Microsoft Solitaire Collection — 1 achievement (+10 G)</blockquote>
```

Plus a deletes a message

### /summary_day

`group-summary-day` · input: `/summary_day` · command, supergroup


```
A summary was sent recently. You can ask again in 10 min.
```

### /summary_month

`group-summary-month` · input: `/summary_month` · command, supergroup


```
A summary was sent recently. You can ask again in 10 min.
```

### /hltb in a group

`group-hltb` · input: `/hltb` · command, supergroup


```
Game title? It doesn't have to be exact — I'll show you options.
Reply to this message, or pick one of your recent games:
```

```
[ Microsoft Flight Simulator 2024 ]
[ Call of Duty®: Black Ops Cold War (Windows) ]
[ VALORANT ]
[ THE FINALS ]
[ TEKKEN 8 ]
[ 1/5 ]  [ ▶️ ]
[ ❌ Cancel ]
```

### /connect_steam in a group

`group-connect-steam` · input: `/connect_steam` · command, supergroup


```
Message me privately — we'll connect Steam there.
```

```
[ Open ]→url
```

### /connect_psn in a group

`group-connect-psn` · input: `/connect_psn` · command, supergroup


```
Message me privately — we'll connect PSN there.
```

```
[ Open ]→url
```

### /who → that person's card

`group-who-stats` · input: `who:stats:319472587` · button, supergroup


```
📊 <b>k_maks</b>
🔵 PlayStation: <a href="https://my.playstation.com/profile/kmaks90">kmaks90</a>  ·  251 trophies  ·  level 76

Today:      0 achievements
This month: 29 achievements

<b>Games in the last 30 days</b>
<blockquote expandable>1. 🔵 Marvel&#x27;s Spider-Man Remastered — 26 ach.
2. 🔵 Returnal — 4 ach.
3. 🔵 STAR WARS Jedi: Fallen Order — 4 ach.
4. 🔵 ASTRO’s PLAYROOM — 1 ach.
5. 🔵 Hogwarts Legacy — 1 ach.</blockquote>
```

Plus a deletes a message

Plus a deletes a message

### Hub: publish my achievements

`group-sub-on` · input: `sub:on` · button, supergroup

Draws nothing — only toast «You're already publishing here.».

### Admin: user card → Refresh (PSN)

`admin-sync` · input: `a:sync:psn:319472587` · button, private

> ⚠️ **This screen does not build:** `TypeError: 'str' object is not callable`

### Admin: reset a platform → confirmed

`admin-resetok` · input: `a:resetok:psn:319472587` · button, private

> ⚠️ **This screen does not build:** `ValueError: too many values to unpack (expected 3)`

### Admin: exclude a user

`admin-excl` · input: `a:excl:933710666` · button, private

> ⚠️ **This screen does not build:** `ValueError: not enough values to unpack (expected 4, got 3)`

### Admin: chat → daily summary on/off

`admin-chat-daily-toggle` · input: `a:cds:-1001103247578` · button, private


```
💬 XBOX CG

Состояние:    активен
Публикуется:  5 чел.
Порог редк.:  15%
Итог дня:     нет, в 20:00
Часовой пояс: UTC+3
Мин. G:       0
Антиспам:     3 ач. / 60 мин
Язык:         English

Подписаны: Igor, k_maks, Key Real, Vitaliy, Ｗｈａｌｅｒｉｄｅｒ➑➍
```

```
[ Итог дня: выключен ]
[ Время итога: 20:00 (UTC+3) ▸ ]
[ ‹ Назад ]
```

### Admin: chat → language

`admin-chat-locale` · input: `a:cloc:-1001103247578` · button, private


```
💬 XBOX CG

Состояние:    активен
Публикуется:  5 чел.
Порог редк.:  15%
Итог дня:     да, в 20:00
Часовой пояс: UTC+3
Мин. G:       0
Антиспам:     3 ач. / 60 мин
Язык:         Русский

Подписаны: Igor, k_maks, Key Real, Vitaliy, Ｗｈａｌｅｒｉｄｅｒ➑➍
```

```
[ Порог редкости: 15% ▸ ]
[ Итог дня: включён ▸ ]
[ Антиспам: 3 ач. / 60 мин ▸ ]
[ Язык: Русский ]
[ ⏸ Отключить чат ]
[ 🗑 Сообщения ▸ ]
[ ‹ К списку ]
```

### Admin: chat → rarity threshold

`admin-chat-rare` · input: `a:crt:-1001103247578` · button, private


```
Порог «редкого» достижения в «XBOX CG»: 15%

Пришли новое значение одним числом, например 12 или 7.5 — от 0 до 100.
Действует только на этот чат.
```

```
[ ‹ Назад ]
```

### /unsubscribe → confirmation

`group-unsub-confirm` · input: `unsub:yes:-1001103247578` · button, supergroup

Draws nothing — only toast «That's not your button.».

### /who → cancel

`group-who-cancel` · input: `who:cancel` · button, supergroup

Draws nothing — only deletes a message, toast.

### /summary → show everyone

`group-summary-all` · input: `summary:all:-1001103247578` · button, supergroup


```
📊 <b>since September 1, in full</b>

<b>Total:</b> 122 achievements, +1 900 G
<blockquote>1. Key Real — 56 achievements 💎32 (🟢 56) (+1 670 G)
2. Vitaliy — 32 achievements 💎26 (🟢 5 · 🔵 27) (+220 G)
3. k_maks — 29 achievements (🔵 29) (+0 G)
4. Igor — 5 achievements (🟢 1 · ⚫ 4) (+10 G)
5. Ｗｈａｌｅｒｉｄｅｒ➑➍ — 0 achievements (+0 G)</blockquote>
```

### /delete_last

`group-delete-last` · input: `/delete_last` · command, supergroup


```
🗑 Deleted this message:
“RideTheSun gets an achievement
Call of Duty®: Black Ops Cold War (Windows) (🟢 XBOX)”
```

Plus a deletes a message

Plus a deletes a message

## What the bot sends on its own

### A published PSN trophy (single)

`post-psn-single` · input: `—` · sent by the bot itself

**1. photo with a caption · image: https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/DB6F8A3EA774156DC7585DDC45E5AACD939F84C3.PNG**

```
<b>SuperOmsk</b> получает трофей

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 «<span class="tg-spoiler">Pool Sharks Are The Worst</span>» · редкость 25.8%

<span class="tg-spoiler">Стать добычей акулоида в океане Покитару.</span>
```

**2. photo with a caption · image: https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/DB6F8A3EA774156DC7585DDC45E5AACD939F84C3.PNG**

```
<b>SuperOmsk</b> gets a trophy

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 “<span class="tg-spoiler">Pool Sharks Are The Worst</span>” · 25.8% rarity

<span class="tg-spoiler">Get eaten by a Pool Shark in the Pokitaru Ocean.</span>
```

### A PSN trophy digest (over the digest threshold)

`post-psn-digest` · input: `—` · sent by the bot itself

**1. gallery · 3 image(s): https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/DB6F8A3EA774156DC7585DDC45E5AACD939F84C3.PNG, https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/36848ACBFF1C6505FA439BEFE562E3263F9A5464.PNG, https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/50872504698C5CBB8F4DE80687A01C42F6FB6C2E.PNG**

```
<b>SuperOmsk</b> получает 3 трофея

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 «<span class="tg-spoiler">Pool Sharks Are The Worst</span>» · редкость 25.8%
🥉 «<span class="tg-spoiler">Splashdown!</span>» · редкость 32.9%
🥉 «<span class="tg-spoiler">I Shot Down Your Battleship</span>» · редкость 35.4%
```

**2. photo with a caption · image: https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/DB6F8A3EA774156DC7585DDC45E5AACD939F84C3.PNG**

```
<b>SuperOmsk</b> gets a trophy

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 “<span class="tg-spoiler">Pool Sharks Are The Worst</span>” · 25.8% rarity

<span class="tg-spoiler">Get eaten by a Pool Shark in the Pokitaru Ocean.</span>
```

### The anti-flood digest (mixed platforms)

`post-flood-digest` · input: `—` · sent by the bot itself

**1. photo with a caption · image: https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/36848ACBFF1C6505FA439BEFE562E3263F9A5464.PNG**

```
<b>SuperOmsk</b> gets a trophy

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 “<span class="tg-spoiler">Splashdown!</span>” · 32.9% rarity

<span class="tg-spoiler">Shoot down the hydroharvesters on Pokitaru.</span>
```

**2. photo with a caption · image: https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/50872504698C5CBB8F4DE80687A01C42F6FB6C2E.PNG**

```
<b>SuperOmsk</b> gets a trophy

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 “<span class="tg-spoiler">I Shot Down Your Battleship</span>” · 35.4% rarity

<span class="tg-spoiler">Shoot down the Blarg Battleships on Batalia.</span>
```

### A published Xbox achievement (single)

`post-xbox-single` · input: `—` · sent by the bot itself

**1. gallery · 3 image(s): https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/DB6F8A3EA774156DC7585DDC45E5AACD939F84C3.PNG, https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/36848ACBFF1C6505FA439BEFE562E3263F9A5464.PNG, https://images-eds-ssl.xboxlive.com/image?url=27S1DHqE.cHkmFg4nspsd2r1oWt0fAGaJaS.E_5OsWhaiTV3JUfUUPofXSM22ZiEqNim9Q9e2lYhgjAQ4WERdSKyb6J7UYssXaDFLJNho1zn5m3cc_zFXTTL1ndrk8onxFrw3txopesFr34FMWysfA--**

```
<b>Igor</b> gets 3 achievements

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 “<span class="tg-spoiler">Pool Sharks Are The Worst</span>” · 25.8% rarity
🥉 “<span class="tg-spoiler">Splashdown!</span>” · 32.9% rarity

Microsoft Flight Simulator 2024 (<i>🟢 XBOX</i>)
🏆 “Earning Your Wings” · 15 G
```

**2. photo with a caption · image: https://images-eds-ssl.xboxlive.com/image?url=27S1DHqE.cHkmFg4nspsd2r1oWt0fAGaJaS.E_5OsWhaiTV3JUfUUPofXSM22ZiEqNim9Q9e2lYhgjAQ4WERdSKyb6J7UYssXaDFLJNho1zn5m3cc_zFXTTL1ndrk8onxFrw3txopesFr34FMWysfA--**

```
<b>Whalerider84</b> gets an achievement

Microsoft Flight Simulator 2024 (<i>🟢 XBOX</i>)
🏆 “Earning Your Wings” · 15 G

Earn your Private Pilots License in the Career
```

### The scheduled daily summary

`post-daily` · input: `—` · sent by the bot itself


```
📊 <b>Daily summary</b>, September 13

<b>24 hours:</b> 5 achievements, +75 G
<blockquote expandable>1. Key Real — 5 achievements (🟢 5) (+75 G)
2. Ｗｈａｌｅｒｉｄｅｒ➑➍ — 0 achievements (+0 G)
3. Igor — 0 achievements (+0 G)
4. Vitaliy — 0 achievements (+0 G)
5. k_maks — 0 achievements (+0 G)</blockquote>
```

### The month-end wrap-up

`post-monthly` · input: `—` · sent by the bot itself


```
📊 <b>The month in review</b>

<b>since September 1:</b> 122 achievements, +1 900 G
<blockquote expandable>1. Key Real — 56 achievements 💎32 (🟢 56) (+1 670 G)
2. Vitaliy — 32 achievements 💎26 (🟢 5 · 🔵 27) (+220 G)
3. k_maks — 29 achievements (🔵 29) (+0 G)
4. Igor — 5 achievements (🟢 1 · ⚫ 4) (+10 G)
5. Ｗｈａｌｅｒｉｄｅｒ➑➍ — 0 achievements (+0 G)</blockquote>

<b>Games this month</b>
<blockquote expandable>1. 🔵 Call of Duty®: Black Ops II — 27 trophies 🥇1 🥈2 🥉24
2. 🔵 Marvel&#x27;s Spider-Man Remastered — 26 trophies 🥈4 🥉22
3. 🟢 S.T.A.L.K.E.R. 2: Heart of Chornobyl - Windows Edition — 16 achievements (+340 G)
4. 🟢 Rue Valley — 16 achievements (+715 G)
5. 🟢 Breathedge — 15 achievements (+310 G)
6. 🟢 Call of Duty®: Black Ops Cold War (Windows) — 5 achievements (+75 G)
7. 🟢 Denshattack! — 4 achievements (+120 G)
8. ⚫ G.O.P.O.T.A — 3 achievements
9. 🔵 STAR WARS Jedi: Fallen Order — 3 trophies 🥉3
10. 🟢 Resonance: A Plague Tale Legacy — 2 achievements (+30 G)
11. ⚫ Weird West: Definitive Edition — 1 achievement
12. 🟢 Idle Wizard (Xbox One) — 1 achievement (+100 G)
13. 🟢 DPS IDLE 2 — 1 achievement (+100 G)
14. 🟢 VALORANT — 1 achievement (+100 G)
15. 🟢 Microsoft Solitaire Collection — 1 achievement (+10 G)</blockquote>
```

### Reminder: the Xbox login has gone stale

`post-reminder` · input: `—` · sent by the bot itself

Draws nothing — only silence.

### To the super-admin: a shared platform key died

`post-key-dead` · input: `—` · sent by the bot itself


```
⚠️ Умер общий ключ PSN — все аккаунты PSN разом перестали опрашиваться, пришли новый ключ через админ-панель.
```

### To the super-admin: somebody connected

`post-user-connected` · input: `—` · sent by the bot itself


```
➕ Добавлен пользователь: kmaks90
tg_id 319 472 587 · @keimaks
```

### A game card from /hltb

`hltb-card` · input: `/hltb → picking the game` · card

**photo with a caption · image: https://howlongtobeat.com/games/162277_Mario_Kart_9.png**

```
⏱ <b>Mario Kart World</b> (2025)

Основной сюжет · 4.2 ч
Основной + доп. · 16.5 ч
Полное прохождение · 54.6 ч

Платформы: Nintendo Switch 2

Жанры: Third-Person, Open World, Racing/Driving

<blockquote expandable>Отправляйся в открытое путешествие вместе с Mario и друзьями! Мчись по трассам на огромном мире, где всё связано между собой. Гоняй по травянистым равнинам, оживлённым городам, широким просторам воды, огромным вулканам и многому другому... плюс всё, что находится между ними.</blockquote>

<a href="https://howlongtobeat.com/game/162277">Страница на HowLongToBeat ↗</a>
```

### A game card from /hltb (another game)

`hltb-card-no-description` · input: `/hltb → picking the game` · card

**photo with a caption · image: https://howlongtobeat.com/games/129232_Helldivers_2.jpg**

```
⏱ <b>Helldivers 2</b> (2024)

Основной сюжет · 31.9 ч
Основной + доп. · 65.3 ч
Полное прохождение · 87.1 ч

Платформы: PC, PlayStation 5, Xbox Series X/S

Жанры: Third-Person, Action, Shooter

<blockquote expandable>Пора избавиться от инопланетного мусора. Присоединитесь к Helldivers, чтобы бороться за свободу по всей враждебной галактике в операциях третьего лица.</blockquote>

<a href="https://howlongtobeat.com/game/129232">Страница на HowLongToBeat ↗</a>
```

---

## Where the snapshot and the mockups disagreed

From the review on 2026-09-13. Everything in the first two groups was acted
on the same day; the third is what the method cannot reach.

**Broken in production, not cosmetic:**

1. **"🔄 Обновить" and "🗑 Сброс" in the user card have never worked.**
   `a:sync:*`, `a:reset:*` and `a:resetok:*` unpack
   `callback.data.split(":")` into `_`, which two lines above was assigned
   the translator — so the next `_("key")` raises `TypeError: 'str' object
   is not callable`, and `a:resetok:` additionally unpacks four parts into
   three. The buttons are drawn and tapping them does nothing. Still open;
   the fix does not belong in a docs commit.

**Settled against the mockups (owner decisions, 2026-09-13):**

2. The platform's own label wins: `🔵 PlayStation`, not "PSN", and the
   rarity keeps the word "редкость" before the number. The mockups were
   written shorter than the `.ftl`; the mockups changed.
3. One platform order everywhere — **Xbox, PlayStation, Steam**
   (`constants.platform_display_rank`). /panel had listed Steam second and
   /stats PlayStation second.
4. `tg_id 127 383 366` — an identifier formatted as a quantity, because
   Fluent groups digits in a number. It is passed as a string now.
5. `/help` in a group listed "XBOX and Steam" while offering a PSN button;
   the text names all three platforms now.

**What the snapshot cannot show:**

6. The stale-Xbox-login reminder: no live dead token exists in the
   production data, so there is nothing to render.
7. Anything that continues by typing — only the prompt is captured.
