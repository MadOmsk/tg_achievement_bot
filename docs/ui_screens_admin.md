# UI screens — admin panel (mockups, draft, issue #41)

Layout only, placeholders instead of real data — for editing. Nickname principles
and table contents are documented separately: see [tables.md](tables.md) for
"which rule builds `<ник>` here" (referenced below as **rule A/B/C/D/E**) and for
what actually goes into every `→ table:` line.

## Админ-панель (главная)

```
⚙️ Администрирование  ·  обновлено HH:MM

Пользователей: N (исключено: N)
  XBOX:  N (вход активен: N, без входа: N)
  Steam: N
  PSN:   N
Чатов:          N
API XBOX:  used/limit за окно
API Steam: used/limit за окно
Ключ Steam: <статус>
Ключ PSN:   <статус>
Запросов к PSN за сутки: N
```

Кнопки: список пользователей, список чатов, ключи платформ, глобальные лимиты.

## Список пользователей

```
👥 Пользователи, стр. N/M

→ table: `admin-user-list`
```

Каждая строка списка — кнопка, открывающая карточку этого пользователя.

## Карточка пользователя

```
👤 <имя>, @<username>, tg_id N                            [rule A, полная форма]

🟢 XBOX: <ник>                                            [rule B]
XUID <id>
Вход: <статус>, обновлён N назад
N достижений  ·  🏆 K  ·  сегодня N  ·  gamerscore G
В сети: N назад

⚫ Steam: <ник>                                            [rule B]
id <id>
Вход: <видимость>
N достижений  ·  🏆 K  ·  сегодня N
В сети: N назад

🔵 PSN: <ник>                                             [rule B]
account_id <id>
Вход: <видимость>
N трофеев  ·  сегодня N  ·  уровень L

Подписан: <чаты>
```

Заголовок карточки — единственное место в проекте, где сразу видны все три
Telegram-идентификатора (имя, `@username`, `tg_id`) вместе; это не то же самое,
что rule A из tables.md (та выбирает *один* лучший вариант), а полная,
неусечённая форма специально для админского поиска/сверки.

Кнопки на каждый подключённый блок: `[ 🔄 Обновить X ]  [ 🗑 Сброс X ]`.

## Список чатов

```
💬 Чаты, стр. N/M

→ table: `admin-chat-list`
```

## Карточка чата

```
💬 <название чата>

Состояние:    <активен/неактивен>
Публикуется:  N чел.
Порог редк.:  N%
Итог дня:     да/нет, в HH:MM
Часовой пояс: UTC±N
Мин. G:       N

Подписаны: → table: `admin-chat-subscribers`
```
