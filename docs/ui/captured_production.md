# Снимок интерфейса с боевого бота

Не макет и не дизайн-решение — **снимок того, что боевой бот рисует
сегодня**, снятый 2026-09-13 с кода `e51d044` (то, что развёрнуто на
проде) и read-only копии боевой базы. Дизайнерские решения по-прежнему
живут в [ui_screens_users.md](ui_screens_users.md),
[ui_screens_admin.md](ui_screens_admin.md) и [tables.md](tables.md); этот
файл существует, чтобы их было с чем сверять.

Как снято: `scripts/ui_capture/` — настоящий Dispatcher, настоящие роутеры и
middleware, настоящая база; подменён только сам Telegram, на сессию, которая
записывает исходящий вызов вместо отправки. Поэтому здесь ровно то, что
ушло бы в Telegram: текст (с HTML-разметкой), инлайн-клавиатура по рядам,
и URL картинки или галереи. Никакой сети: платформенные API не трогаются,
а база — копия, не сервер.

Что это не покрывает: вводимый текст (ввод ника Steam, ручной часовой пояс
и т.п.) показан только приглашением, а не последующим ответом; экраны,
которым нужен живой вызов платформы, помечены как несобравшиеся.

Три общих замечания к снимку:

- **Общие ключи** (Steam/PSN/Anthropic) в копии перешифрованы заглушками —
  боевого `FERNET_KEY` на машине разработки нет. На экранах ключей это
  видно как замаскированное значение-заглушку; «жив/мёртв» и раскладка
  настоящие.
- Экраны, которые меняют данные (кнопка языка, тумблеры, подписка), при
  снятии откатываются — иначе следующий экран рисуется по данным, которые
  наснимал сам снимок. Первый заход именно на это и напоролся: половина
  инвентаря вышла по-английски, потому что кнопка языка сработала раньше.
- **Главный чат «XBOX CG» стоит на английском** (`chat_settings.locale =
  en`), поэтому все групповые экраны здесь английские. Это настоящее
  состояние боевой базы, а не артефакт снятия. Личка админа — русская.

---

## Личные экраны

### /start

`start` · вход: `/start` · command / private


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
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить XBOX ]
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить Steam ]
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить PSN ]
[ Обновить ]
```

Плюс удаление сообщения

### /panel

`panel` · вход: `/panel` · command / private


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
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить XBOX ]
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить Steam ]
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить PSN ]
[ Обновить ]
```

Плюс удаление сообщения

### Панель: Обновить

`panel-refresh` · вход: `panel:refresh` · callback / private


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
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить XBOX ]
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить Steam ]
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить PSN ]
[ Обновить ]
```

Плюс всплывашка — «Обновил»

### Панель: часовой пояс

`panel-tz` · вход: `panel:tz` · callback / private


```
🕐 Часовой пояс — по нему считаются «сегодня» и «за месяц».
```

```
[ UTC+2 ]  [ UTC+3 ]  [ UTC+4 ]  [ UTC+5 ]
[ UTC+6 ]  [ UTC+7 ]  [ UTC+9 ]  [ UTC+10 ]
[ Другой ▸ ]
[ ✏️ Ввести вручную ]
```

### Панель: мои чаты

`panel-chatlist` · вход: `panel:chatlist` · callback / private


```
💬 Мои чаты
```

```
[ ✅ XBOX CG ]
[ ✅ test chat ]
[ ‹ Назад ]
```

### Панель: карточка чата

`panel-chat` · вход: `panel:chat:-1001103247578` · callback / private


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

### Панель: режим редкости в чате

`panel-chatrarity` · вход: `panel:chatrarity:-1001103247578` · callback / private


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

### Панель: порог дайджеста

`panel-chatdigest` · вход: `panel:chatdigest:-1001103247578` · callback / private


```
Сводка вместо отдельных сообщений

Если за один раз в одной игре выбито столько достижений или больше — в этот чат уйдёт одно сводное сообщение.
```

```
[ 2 ]  [ 3 ]  [ 4 ]  [ 5 ]
[ 6 ]  [ 8 ]  [ 10 ]  [ • никогда ]
[ ‹ Назад ]
```

### Панель: отписаться от чата (подтверждение)

`panel-chatunsub` · вход: `panel:chatunsub:-1001103247578` · callback / private


```
Перестать публиковать твои достижения в «XBOX CG»?
```

```
[ Да, отписаться ]
[ Отмена ]
```

### Панель: профиль виден другим

`panel-linkstoggle` · вход: `panel:linkstoggle` · callback / private


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
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить XBOX ]
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить Steam ]
[ 👤 Профиль ]→ссылка  [ 🔕 Отключить PSN ]
[ Обновить ]
```

Плюс всплывашка — «Скрыл»

### Панель: язык

`panel-locale` · вход: `panel:locale` · callback / private


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
[ 👤 Profile ]→ссылка  [ 🔕 Disconnect XBOX ]
[ 👤 Profile ]→ссылка  [ 🔕 Disconnect Steam ]
[ 👤 Profile ]→ссылка  [ 🔕 Disconnect PSN ]
[ Refresh ]
```

Плюс всплывашка — «English»

### Панель: отключить Xbox (подтверждение)

`panel-disconnect` · вход: `panel:disconnect` · callback / private


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

`connect-xbox` · вход: `/connect_xbox` · command / private


```
XBOX уже подключён. Если нужно войти заново — сначала /disconnect_xbox.
```

### /disconnect_xbox

`disconnect-xbox` · вход: `/disconnect_xbox` · command / private


```
Отключить XBOX?

Удалю токен и подписки. Историю достижений оставлю — она нужна статистике чата, и при повторном входе старые достижения не хлынут в чат заново.

Само разрешение остаётся в аккаунте Microsoft — убрать его можно только самому: https://account.live.com/consent/Manage
```

```
[ Да, отключить ]
[ Отмена ]
```

### Отмена отключения Xbox

`disconnect-xbox-no` · вход: `disconnect:no` · callback / private

Ничего не рисует — только удаление сообщения, всплывашка.

### Кнопка «войти заново»

`relogin` · вход: `relogin` · callback / private


```
Войди заново — старые достижения в чат не полетят, они уже отмечены как виденные.
```

```
[ Подключить XBOX ]→ссылка
```

### Часовой пояс: ещё

`tz-more` · вход: `tz:more` · callback / private


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

### Часовой пояс: ввести вручную

`tz-manual` · вход: `tz:manual` · callback / private


```
Пришли смещение одним сообщением, со знаком: например +3, -5 или +5:30.
```

### /connect_steam

`connect-steam` · вход: `/connect_steam` · command / private


```
Steam уже подключён: Mad Omsk.
```

### /disconnect_steam

`disconnect-steam` · вход: `/disconnect_steam` · command / private


```
Отключить Steam (Mad Omsk)?
```

```
[ Да, отключить ]
[ Отмена ]
```

### Отмена отключения Steam

`steam-disconnect-no` · вход: `steam:disconnect:no` · callback / private

Ничего не рисует — только удаление сообщения, всплывашка.

### /connect_psn

`connect-psn` · вход: `/connect_psn` · command / private


```
PSN уже подключён: SuperOmsk.
```

### /disconnect_psn

`disconnect-psn` · вход: `/disconnect_psn` · command / private


```
Отключить PSN (SuperOmsk)?
```

```
[ Да, отключить ]
[ Отмена ]
```

### Отмена отключения PSN

`psn-disconnect-no` · вход: `psn:disconnect:no` · callback / private

Ничего не рисует — только удаление сообщения, всплывашка.

### /hltb в личке

`hltb-dm` · вход: `/hltb` · command / private


```
Название игры? Точное не нужно — покажу варианты.
Ответь на это сообщение (реплаем).
```

```
[ ❌ Отмена ]
```

### /hltb: отмена

`hltb-cancel` · вход: `hltb:cancel` · callback / private

Ничего не рисует — только всплывашка, удаление сообщения.

## Панель суперадмина

### /admin — главный экран

`admin` · вход: `/admin` · command / private


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

Плюс удаление сообщения

### Админка: домой

`admin-home` · вход: `a:home` · callback / private


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

### Админка: ключи платформ

`admin-keys` · вход: `a:keys` · callback / private


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

### Админка: ввод ключа Steam

`admin-keyset` · вход: `a:keyset:steam` · callback / private


```
Пришли Steam Web API key одним сообщением — получить его:
https://steamcommunity.com/dev/apikey
```

```
[ Отмена ]
```

### Админка: настройки новых пользователей

`admin-newusers` · вход: `a:newusers` · callback / private


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

### Админка: лимиты отображения

`admin-limits` · вход: `a:limits` · callback / private


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

### Админка: список пользователей

`admin-users` · вход: `a:users:0` · callback / private


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

### Админка: карточка пользователя

`admin-user` · вход: `a:u:319472587` · callback / private


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

### Админка: карточка пользователя (Xbox+Steam)

`admin-user-xbox` · вход: `a:u:127383366` · callback / private


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

### Админка: список чатов

`admin-chats` · вход: `a:chats` · callback / private


```
💬 Чаты  (название · сколько человек публикуется)
```

```
[ XBOX CG · 5 ]
[ test chat · 2 ]
[ ‹ Назад ]
```

### Админка: карточка чата

`admin-chat` · вход: `a:chat:-1001103247578` · callback / private


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

### Админка: чат → итог дня

`admin-chat-summary` · вход: `a:msum:-1001103247578` · callback / private


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

### Админка: чат → антифлуд

`admin-chat-flood` · вход: `a:mflood:-1001103247578` · callback / private


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

### Админка: чат → уборка сообщений

`admin-chat-cleanup` · вход: `a:mdel:-1001103247578` · callback / private


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

### Админка: чат → часовой пояс

`admin-chat-tz` · вход: `a:ctz:-1001103247578` · callback / private


```
Часовой пояс «XBOX CG»: UTC+3
```

```
[ UTC+2 ]  [ • UTC+3 ]  [ UTC+4 ]  [ UTC+5 ]
[ UTC+6 ]  [ UTC+7 ]  [ UTC+9 ]  [ UTC+10 ]
[ ✏️ Ввести вручную ]
[ ‹ Назад ]
```

### Админка: чат → время итога

`admin-chat-time` · вход: `a:ctime:-1001103247578` · callback / private


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

### Админка: чат → стереть сообщения (подтверждение)

`admin-chat-wipe` · вход: `a:cwipe:-1001103247578` · callback / private


```
Стереть 8 сообщений бота в «XBOX CG» за последние 24 часа?

Необратимо. Считаются только сообщения, отправленные с тех пор, как завели
этот учёт, — более старые бот не помнит.
```

```
[ Да, стереть ]
[ Отмена ]
```

### Админка: сброс платформы (подтверждение)

`admin-reset` · вход: `a:reset:psn:319472587` · callback / private

> ⚠️ **Экран не построился:** `TypeError: 'str' object is not callable`

## Групповые экраны

### /help в группе

`group-help` · вход: `/help` · command / supergroup


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
[ 🔗 XBOX ]→ссылка  [ 🎮 Steam ]→ссылка  [ 🎮 PSN ]→ссылка
[ ⚙️ Settings ]→ссылка
```

Плюс GetMe

### /subscribe

`group-subscribe` · вход: `/subscribe` · command / supergroup


```
You're already publishing here.
```

### /unsubscribe

`group-unsubscribe` · вход: `/unsubscribe` · command / supergroup


```
Stop publishing your achievements in this chat?
```

```
[ Yes, unsubscribe ]
[ Cancel ]
```

### /stats

`group-stats` · вход: `/stats` · command / supergroup


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

Плюс удаление сообщения

### /stats @другой

`group-stats-other` · вход: `/stats @keimaks` · command / supergroup


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

Плюс удаление сообщения

### /online

`group-online` · вход: `/online` · command / supergroup


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

`group-who` · вход: `/who` · command / supergroup


```
Whose stats do you want?
```

```
[ Ｗｈａｌｅｒｉｄｅｒ➑➍ ]  [ Key Real ]  [ Vitaliy ]
[ k_maks ]  [ Igor ]  [ Александр ]
[ Cancel ]
```

### /recent

`group-recent` · вход: `/recent` · command / supergroup


```
🕘 <b>Latest achievements</b>
<blockquote expandable>💎 Key Real — 🟢 Call of Duty®: Black Ops Co…, Keep Your Friends Close (+15 G · 7.55%) · 11 h ago
🏆 Key Real — 🟢 Call of Duty®: Black Ops Co…, Fracture Jaw (+15 G · 27.81%) · 11 h ago
💎 Key Real — 🟢 Call of Duty®: Black Ops Co…, Scorched Earth (+15 G · 1.51%) · 11 h ago
🏆 Key Real — 🟢 Call of Duty®: Black Ops Co…, Jack of All Trades (+15 G · 16.38%) · 12 h ago
🏆 Key Real — 🟢 Call of Duty®: Black Ops Co…, Nowhere Left to Run (+15 G · 35.61%) · 12 h ago</blockquote>
```

Плюс удаление сообщения

### /summary

`group-summary` · вход: `/summary` · command / supergroup


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

Плюс удаление сообщения

### /summary_day

`group-summary-day` · вход: `/summary_day` · command / supergroup


```
A summary was sent recently. You can ask again in 10 min.
```

### /summary_month

`group-summary-month` · вход: `/summary_month` · command / supergroup


```
A summary was sent recently. You can ask again in 10 min.
```

### /hltb в группе

`group-hltb` · вход: `/hltb` · command / supergroup


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

### /connect_steam в группе

`group-connect-steam` · вход: `/connect_steam` · command / supergroup


```
Message me privately — we'll connect Steam there.
```

```
[ Open ]→ссылка
```

### /connect_psn в группе

`group-connect-psn` · вход: `/connect_psn` · command / supergroup


```
Message me privately — we'll connect PSN there.
```

```
[ Open ]→ссылка
```

### /who → карточка человека

`group-who-stats` · вход: `who:stats:319472587` · callback / supergroup


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

Плюс удаление сообщения

Плюс удаление сообщения

### Хаб: публиковать мои достижения

`group-sub-on` · вход: `sub:on` · callback / supergroup

Ничего не рисует — только всплывашка «You're already publishing here.».

### Админка: карточка пользователя → Обновить (PSN)

`admin-sync` · вход: `a:sync:psn:319472587` · callback / private

> ⚠️ **Экран не построился:** `TypeError: 'str' object is not callable`

### Админка: сброс платформы → подтверждено

`admin-resetok` · вход: `a:resetok:psn:319472587` · callback / private

> ⚠️ **Экран не построился:** `ValueError: too many values to unpack (expected 3)`

### Админка: исключить пользователя

`admin-excl` · вход: `a:excl:933710666` · callback / private

> ⚠️ **Экран не построился:** `ValueError: not enough values to unpack (expected 4, got 3)`

### Админка: чат → итог дня вкл/выкл

`admin-chat-daily-toggle` · вход: `a:cds:-1001103247578` · callback / private


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

### Админка: чат → язык

`admin-chat-locale` · вход: `a:cloc:-1001103247578` · callback / private


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

### Админка: чат → порог редкости

`admin-chat-rare` · вход: `a:crt:-1001103247578` · callback / private


```
Порог «редкого» достижения в «XBOX CG»: 15%

Пришли новое значение одним числом, например 12 или 7.5 — от 0 до 100.
Действует только на этот чат.
```

```
[ ‹ Назад ]
```

### /unsubscribe → подтверждение

`group-unsub-confirm` · вход: `unsub:yes:-1001103247578` · callback / supergroup

Ничего не рисует — только всплывашка «That's not your button.».

### /who → отмена

`group-who-cancel` · вход: `who:cancel` · callback / supergroup

Ничего не рисует — только удаление сообщения, всплывашка.

### /summary → показать всех

`group-summary-all` · вход: `summary:all:-1001103247578` · callback / supergroup


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

`group-delete-last` · вход: `/delete_last` · command / supergroup


```
🗑 Deleted this message:
“RideTheSun gets an achievement
Call of Duty®: Black Ops Cold War (Windows) (🟢 XBOX)”
```

Плюс удаление сообщения

Плюс удаление сообщения

## Что бот присылает сам

### Опубликованный трофей PSN (одиночный)

`post-psn-single` · вход: `—` · автоматическое сообщение

**картинка: https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/DB6F8A3EA774156DC7585DDC45E5AACD939F84C3.PNG**

```
<b>SuperOmsk</b> получает трофей

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 «<span class="tg-spoiler">Pool Sharks Are The Worst</span>» · редкость 25.8%

<span class="tg-spoiler">Стать добычей акулоида в океане Покитару.</span>
```

### Дайджест трофеев PSN (порог дайджеста пройден)

`post-psn-digest` · вход: `—` · автоматическое сообщение

**3 картинк(и): https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/DB6F8A3EA774156DC7585DDC45E5AACD939F84C3.PNG, https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/36848ACBFF1C6505FA439BEFE562E3263F9A5464.PNG, https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/50872504698C5CBB8F4DE80687A01C42F6FB6C2E.PNG**

```
<b>SuperOmsk</b> получает 3 трофея

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 «<span class="tg-spoiler">Pool Sharks Are The Worst</span>» · редкость 25.8%
🥉 «<span class="tg-spoiler">Splashdown!</span>» · редкость 32.9%
🥉 «<span class="tg-spoiler">I Shot Down Your Battleship</span>» · редкость 35.4%
```

### Дайджест после антифлуда (смешанные платформы)

`post-flood-digest` · вход: `—` · автоматическое сообщение

**3 картинк(и): https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/DB6F8A3EA774156DC7585DDC45E5AACD939F84C3.PNG, https://image.api.playstation.com/trophy/np/NPWR07942_00_006F781DB9EE3B1A96EB9472B006DA21899A916D8F/36848ACBFF1C6505FA439BEFE562E3263F9A5464.PNG, https://images-eds-ssl.xboxlive.com/image?url=27S1DHqE.cHkmFg4nspsd2r1oWt0fAGaJaS.E_5OsWhaiTV3JUfUUPofXSM22ZiEqNim9Q9e2lYhgjAQ4WERdSKyb6J7UYssXaDFLJNho1zn5m3cc_zFXTTL1ndrk8onxFrw3txopesFr34FMWysfA--**

```
<b>Igor</b> получает 3 достижения

Ratchet &amp; Clank™ (<i>🔵 PlayStation</i>)
🥉 «<span class="tg-spoiler">Pool Sharks Are The Worst</span>» · редкость 25.8%
🥉 «<span class="tg-spoiler">Splashdown!</span>» · редкость 32.9%

Microsoft Flight Simulator 2024 (<i>🟢 XBOX</i>)
🏆 «Earning Your Wings» · 15 G
```

### Опубликованное достижение Xbox (одиночное)

`post-xbox-single` · вход: `—` · автоматическое сообщение

**картинка: https://images-eds-ssl.xboxlive.com/image?url=27S1DHqE.cHkmFg4nspsd2r1oWt0fAGaJaS.E_5OsWhaiTV3JUfUUPofXSM22ZiEqNim9Q9e2lYhgjAQ4WERdSKyb6J7UYssXaDFLJNho1zn5m3cc_zFXTTL1ndrk8onxFrw3txopesFr34FMWysfA--**

```
<b>Whalerider84</b> получает достижение

Microsoft Flight Simulator 2024 (<i>🟢 XBOX</i>)
🏆 «Earning Your Wings» · 15 G

Получите лицензию частного пилота в режиме «Карьера»
```

### Итог дня (плановая рассылка)

`post-daily` · вход: `—` · автоматическое сообщение


```
📊 <b>Итог дня</b>, 12 сентября

<b>24 часа:</b> 5 достижений, +75 G
<blockquote expandable>1. Key Real — 5 достижений (🟢 5) (+75 G)
2. Ｗｈａｌｅｒｉｄｅｒ➑➍ — 0 достижений (+0 G)
3. Igor — 0 достижений (+0 G)
4. Vitaliy — 0 достижений (+0 G)
5. k_maks — 0 достижений (+0 G)</blockquote>
```

### Итоги за месяц (последний день месяца)

`post-monthly` · вход: `—` · автоматическое сообщение


```
📊 <b>Итоги за месяц</b>

<b>с 1 сентября:</b> 122 достижения, +1 900 G
<blockquote expandable>1. Key Real — 56 достижений 💎32 (🟢 56) (+1 670 G)
2. Vitaliy — 32 достижения 💎26 (🟢 5 · 🔵 27) (+220 G)
3. k_maks — 29 достижений (🔵 29) (+0 G)
4. Igor — 5 достижений (🟢 1 · ⚫ 4) (+10 G)
5. Ｗｈａｌｅｒｉｄｅｒ➑➍ — 0 достижений (+0 G)</blockquote>

<b>Игры за месяц</b>
<blockquote expandable>1. 🔵 Call of Duty®: Black Ops II — 27 трофеев 🥇1 🥈2 🥉24
2. 🔵 Marvel&#x27;s Spider-Man Remastered — 26 трофеев 🥈4 🥉22
3. 🟢 S.T.A.L.K.E.R. 2: Heart of Chornobyl - Windows Edition — 16 достижений (+340 G)
4. 🟢 Rue Valley — 16 достижений (+715 G)
5. 🟢 Breathedge — 15 достижений (+310 G)
6. 🟢 Call of Duty®: Black Ops Cold War (Windows) — 5 достижений (+75 G)
7. 🟢 Denshattack! — 4 достижения (+120 G)
8. ⚫ G.O.P.O.T.A — 3 достижения
9. 🔵 STAR WARS Jedi: Fallen Order — 3 трофея 🥉3
10. 🟢 Resonance: A Plague Tale Legacy — 2 достижения (+30 G)
11. ⚫ Weird West: Definitive Edition — 1 достижение
12. 🟢 Idle Wizard (Xbox One) — 1 достижение (+100 G)
13. 🟢 DPS IDLE 2 — 1 достижение (+100 G)
14. 🟢 VALORANT — 1 достижение (+100 G)
15. 🟢 Microsoft Solitaire Collection — 1 достижение (+10 G)</blockquote>
```

### Напоминание о протухшем входе Xbox

`post-reminder` · вход: `—` · автоматическое сообщение

Ничего не рисует — только тишина.

### Суперадмину: общий ключ платформы умер

`post-key-dead` · вход: `—` · автоматическое сообщение


```
⚠️ The shared PSN key is dead — every PSN account stopped being polled at once, send a new key via the admin panel.
```

### Суперадмину: пользователь подключился

`post-user-connected` · вход: `—` · автоматическое сообщение


```
➕ User added: kmaks90
tg_id 319,472,587 · @keimaks
```

### Карточка игры /hltb (с описанием)

`hltb-card` · вход: `/hltb → выбор игры` · карточка

**картинка: https://howlongtobeat.com/games/162277_Mario_Kart_9.png**

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

### Карточка игры /hltb (описания нет)

`hltb-card-no-description` · вход: `/hltb → выбор игры` · карточка

**картинка: https://howlongtobeat.com/games/129232_Helldivers_2.jpg**

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

## Что снимок не сошёлся с макетами

Собрано при сверке 2026-09-13. Поломки — в issues, расхождения макета и
кода — к решению владельца, что из них правда.

**Сломано в бою (не косметика):**

1. **«🔄 Обновить» и «🗑 Сброс» в карточке пользователя не работают ни
   разу.** `a:sync:*`, `a:reset:*` и `a:resetok:*` распаковывают
   `callback.data.split(":")` в переменную `_`, которой двумя строками
   выше присвоен переводчик — дальше первый же `_("ключ")` падает с
   `TypeError: 'str' object is not callable`, а `a:resetok:` ещё и
   разбирает четыре части в три. Кнопки нарисованы, нажатие не делает
   ничего. Есть и на боевом, и в ветке.

**Расходится с тем, что написано в макетах:**

2. `(🔵 PlayStation)` в карточке достижения против `(🔵 PSN)` в
   [ui_screens_users.md](ui_screens_users.md); и «редкость 12.8%» против
   «12.8%» там же.
3. Порядок платформ: `/panel` — XBOX → Steam → PSN, `/stats` —
   XBOX → PlayStation → Steam. Макет обещает один порядок для обоих.
4. `tg_id 127 383 366` в карточке суперадмина — идентификатор с
   разделителями разрядов, как будто это количество. CLAUDE.md требует
   «a plain `tg_id N`».
5. `/help` в группе перечисляет «XBOX and Steam» — PSN в тексте нет, хотя
   кнопка PSN в том же экране есть.

**Чего в снимке нет, хотя экран существует:**

6. Напоминание о протухшем входе XBOX: на боевых данных живых
   протухших токенов нет, рисовать нечего.
7. Всё, что продолжается вводом текста (ник Steam, Online ID, ручной
   часовой пояс, ключ платформы) — снято только приглашение.
