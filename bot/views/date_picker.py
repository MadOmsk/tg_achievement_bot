"""Inline keyboards and helpers for historical date navigation (#75).

Provides month and day navigation bars (◀️ | 📅 Date | ▶️) and calendar pickers
for /stats, /summary_month, and /summary_day.
"""

from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MONTH_NAMES_RU = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)

MONTH_NAMES_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

MONTH_SHORT_RU = (
    "Янв",
    "Фев",
    "Мар",
    "Апр",
    "Май",
    "Июн",
    "Июл",
    "Авг",
    "Сен",
    "Окт",
    "Ноя",
    "Дек",
)

MONTH_SHORT_EN = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)

DAY_GENITIVE_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def format_month_year(year: int, month: int, locale: str = "ru") -> str:
    names = MONTH_NAMES_RU if locale == "ru" else MONTH_NAMES_EN
    month_str = names[month - 1]
    return f"{month_str} {year}"


def format_day_month(d: date, locale: str = "ru") -> str:
    if locale == "ru":
        month_str = DAY_GENITIVE_RU[d.month - 1]
        return f"{d.day} {month_str}"
    month_str = MONTH_SHORT_EN[d.month - 1]
    return f"{d.day} {month_str}"


def prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


# ------------------------------------------------------------- /stats navigation


def stats_navigation_keyboard(
    target_tg_id: int,
    year: int,
    month: int,
    now_year: int,
    now_month: int,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    pyear, pmonth = prev_month(year, month)
    nyear, nmonth = next_month(year, month)

    is_current_or_future = (year, month) >= (now_year, now_month)

    prev_cb = f"st:nav:{target_tg_id}:{pyear}:{pmonth}"
    cal_cb = f"st:cal:{target_tg_id}:{year}"
    next_cb = f"st:nav:{target_tg_id}:{nyear}:{nmonth}"

    month_label = format_month_year(year, month, locale)
    buttons: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="◀️", callback_data=prev_cb),
        InlineKeyboardButton(text=f"📅 {month_label}", callback_data=cal_cb),
    ]

    if not is_current_or_future:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=next_cb))

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def stats_month_calendar_keyboard(
    target_tg_id: int,
    year: int,
    now_year: int,
    now_month: int,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    # Row 1: Year switcher
    prev_y_cb = f"st:cal:{target_tg_id}:{year - 1}"
    next_y_cb = f"st:cal:{target_tg_id}:{year + 1}"
    year_row = [
        InlineKeyboardButton(text=f"◀️ {year - 1}", callback_data=prev_y_cb),
        InlineKeyboardButton(text=f"• {year} •", callback_data="noop"),
    ]
    if year < now_year:
        year_row.append(InlineKeyboardButton(text=f"{year + 1} ▶️", callback_data=next_y_cb))
    rows.append(year_row)

    # 4x3 month grid
    short_names = MONTH_SHORT_RU if locale == "ru" else MONTH_SHORT_EN
    month_grid: list[InlineKeyboardButton] = []
    for m in range(1, 13):
        if (year, m) > (now_year, now_month):
            txt = f"· {short_names[m - 1]} ·"
            month_grid.append(InlineKeyboardButton(text=txt, callback_data="noop"))
        else:
            cb = f"st:nav:{target_tg_id}:{year}:{m}"
            month_grid.append(InlineKeyboardButton(text=short_names[m - 1], callback_data=cb))

    for i in range(0, 12, 3):
        rows.append(month_grid[i : i + 3])

    # Back button
    back_cb = f"st:nav:{target_tg_id}:{now_year}:{now_month}"
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ----------------------------------------------------- /summary_month navigation


def summary_month_navigation_keyboard(
    year: int,
    month: int,
    now_year: int,
    now_month: int,
    locale: str = "ru",
    *,
    has_more: bool = False,
) -> InlineKeyboardMarkup:
    pyear, pmonth = prev_month(year, month)
    nyear, nmonth = next_month(year, month)

    is_current_or_future = (year, month) >= (now_year, now_month)

    prev_cb = f"sm:nav:{pyear}:{pmonth}"
    cal_cb = f"sm:cal:{year}"
    next_cb = f"sm:nav:{nyear}:{nmonth}"

    month_label = format_month_year(year, month, locale)
    nav_row: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="◀️", callback_data=prev_cb),
        InlineKeyboardButton(text=f"📅 {month_label}", callback_data=cal_cb),
    ]

    if not is_current_or_future:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=next_cb))

    rows = [nav_row]
    if has_more:
        all_cb = (
            "summary:all:month"
            if (year, month) == (now_year, now_month)
            else f"summary:all:month:{year}:{month}"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="Показать всех (за месяц)" if locale == "ru" else "Show all (month)",
                    callback_data=all_cb,
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def summary_month_calendar_keyboard(
    year: int,
    now_year: int,
    now_month: int,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    # Row 1: Year switcher
    prev_y_cb = f"sm:cal:{year - 1}"
    next_y_cb = f"sm:cal:{year + 1}"
    year_row = [
        InlineKeyboardButton(text=f"◀️ {year - 1}", callback_data=prev_y_cb),
        InlineKeyboardButton(text=f"• {year} •", callback_data="noop"),
    ]
    if year < now_year:
        year_row.append(InlineKeyboardButton(text=f"{year + 1} ▶️", callback_data=next_y_cb))
    rows.append(year_row)

    # 4x3 month grid
    short_names = MONTH_SHORT_RU if locale == "ru" else MONTH_SHORT_EN
    month_grid: list[InlineKeyboardButton] = []
    for m in range(1, 13):
        if (year, m) > (now_year, now_month):
            txt = f"· {short_names[m - 1]} ·"
            month_grid.append(InlineKeyboardButton(text=txt, callback_data="noop"))
        else:
            cb = f"sm:nav:{year}:{m}"
            month_grid.append(InlineKeyboardButton(text=short_names[m - 1], callback_data=cb))

    for i in range(0, 12, 3):
        rows.append(month_grid[i : i + 3])

    back_cb = f"sm:nav:{now_year}:{now_month}"
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ------------------------------------------------------- /summary_day navigation


def summary_day_navigation_keyboard(
    target_date: date,
    now_date: date,
    locale: str = "ru",
    *,
    has_more: bool = False,
) -> InlineKeyboardMarkup:
    prev_d = target_date - timedelta(days=1)
    next_d = target_date + timedelta(days=1)

    is_today_or_future = target_date >= now_date

    prev_cb = f"sd:nav:{prev_d.isoformat()}"
    cal_cb = f"sd:cal:{target_date.isoformat()}"
    next_cb = f"sd:nav:{next_d.isoformat()}"

    day_label = format_day_month(target_date, locale)
    nav_row: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="◀️", callback_data=prev_cb),
        InlineKeyboardButton(text=f"📅 {day_label}", callback_data=cal_cb),
    ]

    if not is_today_or_future:
        nav_row.append(InlineKeyboardButton(text="▶️", callback_data=next_cb))

    rows = [nav_row]
    if has_more:
        all_cb = (
            "summary:all:day"
            if target_date == now_date
            else f"summary:all:day:{target_date.isoformat()}"
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="Показать всех (24ч)" if locale == "ru" else "Show all (24h)",
                    callback_data=all_cb,
                )
            ]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def summary_day_calendar_keyboard(
    target_date: date,
    now_date: date,
    locale: str = "ru",
) -> InlineKeyboardMarkup:
    """14-day calendar picker grid (last 2 weeks up to today)."""
    rows: list[list[InlineKeyboardButton]] = []
    days: list[InlineKeyboardButton] = []

    # 14 days from (now_date - 13 days) to now_date
    for offset in range(13, -1, -1):
        d = now_date - timedelta(days=offset)
        label = format_day_month(d, locale)
        mark = "• " if d == target_date else ""
        cb = f"sd:nav:{d.isoformat()}"
        days.append(InlineKeyboardButton(text=f"{mark}{label}", callback_data=cb))

    # 2 rows of 7 days
    for i in range(0, 14, 7):
        rows.append(days[i : i + 7])

    back_cb = f"sd:nav:{now_date.isoformat()}"
    rows.append([InlineKeyboardButton(text="↩️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
