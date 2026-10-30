"""Time zones by place, not by offset (owner, 2026-10-30).

A person's or a chat's zone is an IANA name (`Europe/Vilnius`), so a summer
clock change follows by itself; one set before is a plain offset in minutes,
read as a fixed zone. `Tz` is either — or None, UTC. The picker offers
`ZONES`, Windows' way: a row a clock, its cities after it; any other valid
name (a phone's own) is kept too, named by its city part.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Tz = int | str | None

# The picker's rows, as Windows lists its zones (owner, 2026-10-30): one row a
# clock, its cities after it — (the zone stored, Russian, English, the other
# zones the same row stands for, so a phone in Vilnius finds the Kyiv row).
ZONES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "America/Los_Angeles",
        "Лос-Анджелес, Ванкувер",
        "Los Angeles, Vancouver",
        ("America/Vancouver",),
    ),
    ("America/Denver", "Денвер", "Denver", ()),
    ("America/Chicago", "Чикаго", "Chicago", ()),
    ("America/New_York", "Нью-Йорк, Торонто", "New York, Toronto", ("America/Toronto",)),
    ("America/Sao_Paulo", "Сан-Паулу", "São Paulo", ()),
    (
        "Europe/London",
        "Дублин, Лиссабон, Лондон",
        "Dublin, Lisbon, London",
        ("Europe/Dublin", "Europe/Lisbon"),
    ),
    (
        "Europe/Berlin",
        "Амстердам, Берлин, Берн, Вена, Осло, Рим, Стокгольм",
        "Amsterdam, Berlin, Bern, Oslo, Rome, Stockholm, Vienna",
        (
            "Europe/Amsterdam",
            "Europe/Zurich",
            "Europe/Vienna",
            "Europe/Oslo",
            "Europe/Rome",
            "Europe/Stockholm",
        ),
    ),
    (
        "Europe/Prague",
        "Белград, Братислава, Будапешт, Любляна, Прага",
        "Belgrade, Bratislava, Budapest, Ljubljana, Prague",
        ("Europe/Belgrade", "Europe/Bratislava", "Europe/Budapest", "Europe/Ljubljana"),
    ),
    (
        "Europe/Paris",
        "Брюссель, Копенгаген, Мадрид, Париж",
        "Brussels, Copenhagen, Madrid, Paris",
        ("Europe/Brussels", "Europe/Copenhagen", "Europe/Madrid"),
    ),
    (
        "Europe/Warsaw",
        "Варшава, Загреб, Сараево, Скопье",
        "Sarajevo, Skopje, Warsaw, Zagreb",
        ("Europe/Zagreb", "Europe/Sarajevo", "Europe/Skopje"),
    ),
    ("Europe/Kaliningrad", "Калининград", "Kaliningrad", ()),
    (
        "Europe/Kyiv",
        "Вильнюс, Киев, Рига, София, Таллин, Хельсинки",
        "Helsinki, Kyiv, Riga, Sofia, Tallinn, Vilnius",
        ("Europe/Vilnius", "Europe/Riga", "Europe/Sofia", "Europe/Tallinn", "Europe/Helsinki"),
    ),
    ("Europe/Bucharest", "Афины, Бухарест", "Athens, Bucharest", ("Europe/Athens",)),
    ("Europe/Chisinau", "Кишинёв", "Chisinau", ()),
    ("Asia/Jerusalem", "Иерусалим", "Jerusalem", ()),
    ("Europe/Moscow", "Москва, Санкт-Петербург", "Moscow, St. Petersburg", ()),
    ("Europe/Minsk", "Минск", "Minsk", ()),
    ("Europe/Istanbul", "Стамбул", "Istanbul", ()),
    ("Europe/Samara", "Самара, Ижевск", "Samara, Izhevsk", ()),
    ("Asia/Dubai", "Абу-Даби, Дубай", "Abu Dhabi, Dubai", ()),
    ("Asia/Baku", "Баку", "Baku", ()),
    ("Asia/Tbilisi", "Тбилиси", "Tbilisi", ()),
    ("Asia/Yerevan", "Ереван", "Yerevan", ()),
    ("Asia/Yekaterinburg", "Екатеринбург", "Yekaterinburg", ()),
    ("Asia/Almaty", "Алматы, Астана", "Almaty, Astana", ()),
    (
        "Asia/Tashkent",
        "Ашхабад, Душанбе, Ташкент",
        "Ashgabat, Dushanbe, Tashkent",
        ("Asia/Ashgabat", "Asia/Dushanbe"),
    ),
    ("Asia/Kolkata", "Мумбаи, Нью-Дели", "Mumbai, New Delhi", ()),
    ("Asia/Omsk", "Омск", "Omsk", ()),
    ("Asia/Bishkek", "Бишкек", "Bishkek", ()),
    ("Asia/Novosibirsk", "Новосибирск", "Novosibirsk", ()),
    ("Asia/Krasnoyarsk", "Красноярск", "Krasnoyarsk", ()),
    (
        "Asia/Bangkok",
        "Бангкок, Джакарта, Ханой",
        "Bangkok, Hanoi, Jakarta",
        ("Asia/Jakarta", "Asia/Ho_Chi_Minh"),
    ),
    ("Asia/Irkutsk", "Иркутск", "Irkutsk", ()),
    (
        "Asia/Shanghai",
        "Гонконг, Пекин, Сингапур",
        "Beijing, Hong Kong, Singapore",
        ("Asia/Hong_Kong", "Asia/Singapore"),
    ),
    ("Asia/Yakutsk", "Якутск", "Yakutsk", ()),
    ("Asia/Seoul", "Сеул", "Seoul", ()),
    ("Asia/Tokyo", "Токио", "Tokyo", ()),
    ("Asia/Vladivostok", "Владивосток", "Vladivostok", ()),
    (
        "Australia/Sydney",
        "Канберра, Мельбурн, Сидней",
        "Canberra, Melbourne, Sydney",
        ("Australia/Melbourne",),
    ),
    ("Asia/Magadan", "Магадан", "Magadan", ()),
    ("Asia/Kamchatka", "Петропавловск-Камчатский", "Petropavlovsk-Kamchatsky", ()),
)
_NAMES = {z[0]: (z[1], z[2]) for z in ZONES}
# A zone a row stands for -> the row's own zone.
_ROW_OF = {member: z[0] for z in ZONES for member in (z[0], *z[3])}
# Old names a phone may still report, for the ones in use now.
_RENAMED = {
    "Europe/Kiev": "Europe/Kyiv",
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Rangoon": "Asia/Yangon",
    "Europe/Uzhgorod": "Europe/Kyiv",
    "Europe/Zaporozhye": "Europe/Kyiv",
}


def current_name(name: str) -> str:
    """A zone's name as it is now (`Europe/Kiev` is `Europe/Kyiv`)."""
    return _RENAMED.get(name, name)


@lru_cache(maxsize=256)
def _named(name: str) -> tzinfo | None:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def valid(name: str) -> bool:
    """Whether `name` is a time zone this server knows."""
    return bool(name) and "/" in name and _named(name) is not None


def zone(tz: Tz) -> tzinfo:
    """The zone itself: a name's, an offset's fixed one, UTC for none."""
    if isinstance(tz, str):
        return _named(tz) or UTC
    if tz:
        return timezone(timedelta(minutes=int(tz)))
    return UTC


def local_now(tz: Tz, now: datetime | None = None) -> datetime:
    """Now (or `now`) on the zone's own clock, as an aware datetime."""
    return (now or datetime.now(UTC)).astimezone(zone(tz))


def midnight_utc(day: date, tz: Tz) -> datetime:
    """The UTC instant a local day starts in the zone."""
    return datetime.combine(day, time(0), tzinfo=zone(tz)).astimezone(UTC)


def offset_minutes(tz: Tz, now: datetime | None = None) -> int:
    """The zone's offset from UTC now, in minutes (summer time included)."""
    delta = local_now(tz, now).utcoffset() or timedelta(0)
    return int(delta.total_seconds() // 60)


def format_offset(minutes: int) -> str:
    """`UTC+3`, `UTC−3:30`, as every screen shows an offset."""
    from bot.util import utc_offset_label

    return utc_offset_label(minutes)


def place(tz: Tz, locale: str) -> str | None:
    """The place a zone is named by in `locale`: one offered by its name, any
    other by its city part (`America/Sao_Paulo` -> "Sao Paulo"); None for a
    bare offset or a fixed `Etc/` zone."""
    if not isinstance(tz, str) or tz.startswith("Etc/") or "/" not in tz:
        return None
    names = _NAMES.get(_ROW_OF.get(tz, tz))
    if names:
        return names[0] if locale == "ru" else names[1]
    return tz.rsplit("/", 1)[1].replace("_", " ")


def row_of(name: str) -> str | None:
    """The picker's row a zone is in (`Europe/Vilnius` -> `Europe/Kyiv`)."""
    return _ROW_OF.get(current_name(name))


def label(tz: Tz, locale: str, now: datetime | None = None) -> str:
    """As Windows names a zone: `(UTC+02:00) Вильнюс, Киев, Рига…` (UTC+03:00
    in summer — the offset is today's), or `(UTC+05:30)` with no place."""
    offset = _bracket(offset_minutes(tz, now))
    where = place(tz, locale)
    return f"{offset} {where}" if where else offset


def _bracket(minutes: int) -> str:
    sign = "−" if minutes < 0 else "+"
    hours, rest = divmod(abs(minutes), 60)
    return f"(UTC{sign}{hours:02d}:{rest:02d})"


def choices(locale: str, now: datetime | None = None) -> list[dict[str, object]]:
    """The picker's rows, by their offset now, then as listed."""
    rows = [
        {
            "id": name,
            "name": place(name, locale),
            "offset": offset_minutes(name, now),
            "label": label(name, locale, now),
        }
        for name, _ru, _en, _members in ZONES
        if _named(name) is not None
    ]
    rows.sort(key=lambda r: int(r["offset"]))  # type: ignore[call-overload]
    return rows
