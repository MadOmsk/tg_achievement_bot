# UI screens — user-facing (mockups, draft, issue #41)

Layout only, placeholders instead of real data — for editing. Nickname principles
and table contents are documented separately: see [tables.md](tables.md) for
"which rule builds `<ник>` here" (referenced below as **rule A/B/C/D/E**) and for
what actually goes into every `→ table:` line.

## /stats

```
📊 <Ник/Имя>                                              [rule A]
🟢 XBOX: <ник>  ·  N достижений  ·  🏆 K  ·  gamerscore G     [rule B]
⚫ Steam: <ник>  ·  N достижений  ·  🏆 K                     [rule B]
🔵 PlayStation: <ник>  ·  N трофеев  ·  уровень L             [rule B]

Сегодня:   N достижений
За месяц:  N достижений (🟢 N · ⚫ N) (+G G)

→ table: `stats-recent-games`
```

## /panel

```
👤 <ник>                                                  [rule A]
🟢 XBOX: <ник>  ·  N достижений  ·  🏆 K  ·  gamerscore G     [rule B]
⚫ Steam: <ник>  ·  N достижений  ·  🏆 K                     [rule B]
🔵 PlayStation: <ник>  ·  N трофеев  ·  уровень L             [rule B]

Вход XBOX:   <статус токена>
Вход Steam:  <ник>  ·  <видимость ачивок>                     [rule B]
Вход PSN:    <ник>  ·  <видимость трофеев>                    [rule B]
Публикация:  <чаты>
Сейчас:      <онлайн/оффлайн, во что играет>

Часовой пояс: UTC±N
```

Кнопки:
```
[ Часовой пояс: UTC±N ]
[ Мои чаты ]
[ Синхронизировать ]
[ Профиль виден другим: да/нет ]
[ Профиль | Отключить XBOX ]     (или [ 🎮 Подключить Xbox ], если не подключён)
[ Профиль | Отключить Steam ]    (или [ 🎮 Подключить Steam ])
[ Профиль | Отключить PSN ]      (или [ 🎮 Подключить PSN ])
[ Обновить ]
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

## /summary (день + месяц)

```
📊 Итог дня, <дата>

24 часа: N достижений, +G G
→ table: `summary-leaderboard-day`

с 1 <месяц>: N достижений, +G G
→ table: `summary-leaderboard-month`

→ table: `summary-top-games-month`
```

## /summary_day

```
📊 Итог дня, <дата>

24 часа: N достижений, +G G
→ table: `summary-leaderboard-day`
```

## /summary_month

```
📊 Итоги за месяц

с 1 <месяц>: N достижений, +G G
→ table: `summary-leaderboard-month`

→ table: `summary-top-games-month`
```
