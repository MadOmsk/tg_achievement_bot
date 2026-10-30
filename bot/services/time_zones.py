"""Time zones by place, not by offset (owner, 2026-10-30).

A person's or a chat's zone is an IANA name (`Europe/Vilnius`), so a summer
clock change follows by itself; one set before is a plain offset in minutes,
read as a fixed zone. `Tz` is either — or None, UTC. The picker offers
`ZONES`, named in the reader's language; any other valid name (a phone's own)
is kept too, named by its city part.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

Tz = int | str | None

# The places offered, by (IANA name, Russian, English). Russia's own first by
# its zones, then the neighbours this community lives in, then the world.
ZONES: tuple[tuple[str, str, str], ...] = (
    ("Europe/Kaliningrad", "Калининград", "Kaliningrad"),
    ("Europe/Moscow", "Москва", "Moscow"),
    ("Europe/Samara", "Самара", "Samara"),
    ("Asia/Yekaterinburg", "Екатеринбург", "Yekaterinburg"),
    ("Asia/Omsk", "Омск", "Omsk"),
    ("Asia/Novosibirsk", "Новосибирск", "Novosibirsk"),
    ("Asia/Krasnoyarsk", "Красноярск", "Krasnoyarsk"),
    ("Asia/Irkutsk", "Иркутск", "Irkutsk"),
    ("Asia/Yakutsk", "Якутск", "Yakutsk"),
    ("Asia/Vladivostok", "Владивосток", "Vladivostok"),
    ("Asia/Magadan", "Магадан", "Magadan"),
    ("Asia/Kamchatka", "Петропавловск-Камчатский", "Petropavlovsk-Kamchatsky"),
    ("Europe/Minsk", "Минск", "Minsk"),
    ("Europe/Kyiv", "Киев", "Kyiv"),
    ("Europe/Chisinau", "Кишинёв", "Chisinau"),
    ("Europe/Vilnius", "Вильнюс", "Vilnius"),
    ("Europe/Riga", "Рига", "Riga"),
    ("Europe/Tallinn", "Таллин", "Tallinn"),
    ("Europe/Helsinki", "Хельсинки", "Helsinki"),
    ("Europe/Warsaw", "Варшава", "Warsaw"),
    ("Europe/Prague", "Прага", "Prague"),
    ("Europe/Berlin", "Берлин", "Berlin"),
    ("Europe/Paris", "Париж", "Paris"),
    ("Europe/Madrid", "Мадрид", "Madrid"),
    ("Europe/Rome", "Рим", "Rome"),
    ("Europe/Amsterdam", "Амстердам", "Amsterdam"),
    ("Europe/London", "Лондон", "London"),
    ("Europe/Lisbon", "Лиссабон", "Lisbon"),
    ("Europe/Bucharest", "Бухарест", "Bucharest"),
    ("Europe/Sofia", "София", "Sofia"),
    ("Europe/Athens", "Афины", "Athens"),
    ("Europe/Belgrade", "Белград", "Belgrade"),
    ("Europe/Istanbul", "Стамбул", "Istanbul"),
    ("Asia/Tbilisi", "Тбилиси", "Tbilisi"),
    ("Asia/Yerevan", "Ереван", "Yerevan"),
    ("Asia/Baku", "Баку", "Baku"),
    ("Asia/Almaty", "Алматы", "Almaty"),
    ("Asia/Tashkent", "Ташкент", "Tashkent"),
    ("Asia/Bishkek", "Бишкек", "Bishkek"),
    ("Asia/Dushanbe", "Душанбе", "Dushanbe"),
    ("Asia/Ashgabat", "Ашхабад", "Ashgabat"),
    ("Asia/Jerusalem", "Иерусалим", "Jerusalem"),
    ("Asia/Dubai", "Дубай", "Dubai"),
    ("Asia/Kolkata", "Дели", "Delhi"),
    ("Asia/Bangkok", "Бангкок", "Bangkok"),
    ("Asia/Shanghai", "Пекин", "Beijing"),
    ("Asia/Seoul", "Сеул", "Seoul"),
    ("Asia/Tokyo", "Токио", "Tokyo"),
    ("Australia/Sydney", "Сидней", "Sydney"),
    ("America/New_York", "Нью-Йорк", "New York"),
    ("America/Chicago", "Чикаго", "Chicago"),
    ("America/Denver", "Денвер", "Denver"),
    ("America/Los_Angeles", "Лос-Анджелес", "Los Angeles"),
)
_NAMES = {z[0]: (z[1], z[2]) for z in ZONES}
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
    names = _NAMES.get(tz)
    if names:
        return names[0] if locale == "ru" else names[1]
    return tz.rsplit("/", 1)[1].replace("_", " ")


def label(tz: Tz, locale: str, now: datetime | None = None) -> str:
    """`Вильнюс · UTC+2` (UTC+3 in summer), or `UTC+5:30` with no place."""
    offset = format_offset(offset_minutes(tz, now))
    where = place(tz, locale)
    return f"{where} · {offset}" if where else offset


def choices(locale: str, now: datetime | None = None) -> list[dict[str, object]]:
    """The offered zones for a picker, by their offset now, then name."""
    rows = [
        {"id": name, "name": place(name, locale), "offset": offset_minutes(name, now)}
        for name, _ru, _en in ZONES
        if _named(name) is not None
    ]
    rows.sort(key=lambda r: (int(r["offset"]), str(r["name"])))  # type: ignore[call-overload]
    for row in rows:
        row["label"] = f"{row['name']} · {format_offset(int(row['offset']))}"  # type: ignore[call-overload]
    return rows
