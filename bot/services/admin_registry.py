"""Every setting the super-admin changes, described once (#176; owner,
2026-10-08: a new admin setting must appear in the bot and the Mini App at
once).

A row says where the value lives (`global` — `app_settings`; `chat` — one
chat's settings), what it is (a whole number, a decimal, on/off, one of a
list, an hour, a UTC offset), its bounds or its choices, its group and its
label. The bot's `/admin` draws its settings screens from these rows and the
Mini App draws what `/api/mini/admin/settings` sends from them; `set_value`
is the one way either changes a value — parsed, bounded, stored. A new
setting is a row here and its `admin-setting-*` label in `admin.ftl`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal

from bot.constants import DIGEST_CHOICES, DIGEST_NEVER, RarityMode
from bot.i18n import AVAILABLE_LOCALES, LOCALE_NAMES, gettext
from bot.services import post_picture
from bot.services.admin_settings import (
    DEFAULT_RARITY_MODE_DEFAULT,
    DEFAULT_RARITY_MODE_KEY,
    FLOOD_LIMIT_MAX,
    FLOOD_LIMIT_MIN,
    FLOOD_WINDOW_MAX,
    FLOOD_WINDOW_MIN,
    NUMERIC_SETTINGS,
    RARE_THRESHOLD_DEFAULT,
    RARE_THRESHOLD_KEY,
    RARE_THRESHOLD_MAX,
    RARE_THRESHOLD_MIN,
    SHOW_LINKS_DEFAULT,
    SHOW_LINKS_KEY,
    SettingValueError,
)
from bot.util import utc_offset_label

if TYPE_CHECKING:
    from bot.db.repo import ChatTarget, Repo

Scope = Literal["global", "chat"]


class Kind(StrEnum):
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    CHOICE = "choice"
    HOUR = "hour"
    TZ = "tz"


# Every UTC offset some place actually keeps, in minutes (owner, 2026-10-08:
# real ones only — mostly whole hours, a few half and three-quarter hours).
REAL_UTC_OFFSETS_MIN: tuple[int, ...] = tuple(
    sorted(
        [h * 60 for h in range(-12, 15)]
        + [-9 * 60 - 30, -3 * 60 - 30, 3 * 60 + 30, 4 * 60 + 30, 5 * 60 + 30, 5 * 60 + 45]
        + [6 * 60 + 30, 8 * 60 + 45, 9 * 60 + 30, 10 * 60 + 30, 12 * 60 + 45]
    )
)


@dataclass(frozen=True, slots=True)
class Setting:
    key: str
    scope: Scope
    group: str
    kind: Kind
    label: str
    default: Any = None
    min: float | None = None
    max: float | None = None
    # INT with min 0: what a 0 means (an `admin.ftl` key).
    zero_label: str | None = None
    choices: tuple[Any, ...] = ()
    # A line under the label explaining it, an `admin.ftl` key; None if plain.
    hint: str | None = None

    @property
    def zero_means(self) -> Literal["unlimited", "off", "no_delay"] | None:
        if self.kind is not Kind.INT or self.min != 0 or self.zero_label is None:
            return None
        return {
            "admin-unlimited": "unlimited",
            "admin-disabled": "off",
            "admin-no-delay": "no_delay",
        }[self.zero_label]  # type: ignore[return-value]

    def options(self) -> tuple[Any, ...]:
        """The values a pick-one setting takes, in the order they are offered."""
        if self.kind is Kind.CHOICE:
            return self.choices
        if self.kind is Kind.HOUR:
            return tuple(range(24))
        if self.kind is Kind.TZ:
            return REAL_UTC_OFFSETS_MIN
        if self.kind is Kind.BOOL:
            return (True, False)
        return ()


# Which group each numeric setting sits in; one not listed lands in "other".
_NUMERIC_GROUPS = {
    "summary_top_limit": "lists",
    "stats_games_limit": "lists",
    "recent_limit": "lists",
    "hltb_results_limit": "hltb",
    "hltb_page_size": "hltb",
    "system_message_ttl_min": "timers",
    "online_refresh_interval_min": "timers",
    "online_refresh_ttl_hours": "timers",
    "service_health_interval_min": "timers",
    "monthly_summary_delay_minutes": "timers",
    "patch_refresh_hours": "timers",
    "email_codes_per_client_hour": "mail",
    "email_codes_total_hour": "mail",
    "email_checks_per_client_10min": "mail",
    "email_provider_daily_limit": "mail",
}

GROUPS: dict[Scope, tuple[str, ...]] = {
    "global": ("rules", "newcomers", "lists", "hltb", "timers", "mail", "other"),
    "chat": ("main", "summary", "flood"),
}

SETTINGS: tuple[Setting, ...] = (
    # ---- global: rules
    Setting(
        RARE_THRESHOLD_KEY,
        "global",
        "rules",
        Kind.FLOAT,
        "admin-setting-rare-threshold",
        hint="admin-setting-rare-threshold-hint",
        default=RARE_THRESHOLD_DEFAULT,
        min=RARE_THRESHOLD_MIN,
        max=RARE_THRESHOLD_MAX,
    ),
    Setting(
        DEFAULT_RARITY_MODE_KEY,
        "global",
        "newcomers",
        Kind.CHOICE,
        "admin-setting-default-rarity",
        hint="admin-setting-default-rarity-hint",
        default=DEFAULT_RARITY_MODE_DEFAULT,
        choices=(RarityMode.ALL, RarityMode.RARE, RarityMode.HIDDEN),
    ),
    # How many of one person's achievements at once make one digest — one
    # for every chat (owner, 2026-10-08).
    Setting(
        "digest_threshold",
        "global",
        "rules",
        Kind.CHOICE,
        "admin-setting-digest",
        default=3,
        choices=DIGEST_CHOICES,
    ),
    Setting(
        SHOW_LINKS_KEY,
        "global",
        "rules",
        Kind.BOOL,
        "admin-setting-show-links",
        default=SHOW_LINKS_DEFAULT == "1",
    ),
    # A low-resolution post picture enlarged on a square (owner, 2026-10-10;
    # services/post_picture.py): off, on the icon's colour, on the cover.
    Setting(
        post_picture.STYLE_KEY,
        "global",
        "rules",
        Kind.CHOICE,
        "admin-setting-post-picture",
        hint="admin-setting-post-picture-hint",
        default=post_picture.STYLE_DEFAULT,
        choices=post_picture.STYLES,
    ),
    # ---- global: the numbers
    *(
        Setting(
            key,
            "global",
            _NUMERIC_GROUPS.get(key, "other"),
            Kind.INT,
            spec.label,
            default=spec.default,
            min=spec.min,
            max=spec.max,
            zero_label=spec.zero_label if spec.min == 0 else None,
        )
        for key, spec in NUMERIC_SETTINGS.items()
    ),
    # ---- a chat
    Setting("is_active", "chat", "main", Kind.BOOL, "admin-setting-chat-active"),
    Setting(
        "locale",
        "chat",
        "main",
        Kind.CHOICE,
        "admin-setting-chat-locale",
        choices=AVAILABLE_LOCALES,
    ),
    Setting("tz_offset_min", "chat", "main", Kind.TZ, "admin-setting-chat-tz"),
    Setting("daily_summary", "chat", "summary", Kind.BOOL, "admin-setting-chat-summary"),
    Setting("daily_summary_time", "chat", "summary", Kind.HOUR, "admin-setting-chat-summary-time"),
    Setting(
        "flood_limit",
        "chat",
        "flood",
        Kind.INT,
        "admin-setting-chat-flood-limit",
        min=FLOOD_LIMIT_MIN,
        max=FLOOD_LIMIT_MAX,
        zero_label="admin-disabled",
    ),
    Setting(
        "flood_window_minutes",
        "chat",
        "flood",
        Kind.INT,
        "admin-setting-chat-flood-window",
        min=FLOOD_WINDOW_MIN,
        max=FLOOD_WINDOW_MAX,
    ),
)

_BY_KEY: dict[tuple[str, str], Setting] = {(s.scope, s.key): s for s in SETTINGS}


def settings_of(scope: Scope, group: str | None = None) -> list[Setting]:
    """A scope's settings in the order its groups and rows are drawn."""
    rows = [s for s in SETTINGS if s.scope == scope and (group is None or s.group == group)]
    order = {name: i for i, name in enumerate(GROUPS[scope])}
    return sorted(rows, key=lambda s: order[s.group])


def find(scope: Scope, key: str) -> Setting:
    """Raises KeyError for a setting that is not in the registry."""
    return _BY_KEY[(scope, key)]


# ------------------------------------------------------------------ values


def parse(setting: Setting, raw: object) -> Any:
    """`raw` as the setting's value — from a typed message, a button or JSON.
    Raises SettingValueError for anything the setting refuses."""
    low, high = setting.min or 0, setting.max or 0
    if setting.kind is Kind.INT:
        value = _whole(raw, low, high)
        if not low <= value <= high:
            raise SettingValueError("range", low, high)
        return value
    if setting.kind is Kind.FLOAT:
        if isinstance(raw, bool):
            raise SettingValueError("number", low, high)
        try:
            number = float(str(raw).strip().replace(",", "."))
        except ValueError as exc:
            raise SettingValueError("number", low, high) from exc
        if not low <= number <= high:  # NaN fails this too
            raise SettingValueError("range", low, high)
        return number
    if setting.kind is Kind.BOOL:
        if isinstance(raw, bool):
            return raw
        text = str(raw).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off"):
            return False
        raise SettingValueError("choice", 0, 0)
    if setting.kind is Kind.HOUR and isinstance(raw, str) and ":" in raw:
        hours, _, minutes = raw.partition(":")
        if minutes.strip() not in ("00", "0"):
            raise SettingValueError("choice", 0, 23)
        raw = hours
    for option in setting.options():
        if str(option) == str(raw).strip():
            return option
    raise SettingValueError("choice", 0, 0)


def _whole(raw: object, low: float, high: float) -> int:
    if isinstance(raw, bool):
        raise SettingValueError("integer", low, high)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if not raw.is_integer():
            raise SettingValueError("integer", low, high)
        return int(raw)
    text = str(raw).strip()
    if "." in text or "," in text:
        raise SettingValueError("integer", low, high)
    try:
        return int(text)
    except ValueError as exc:
        raise SettingValueError("integer", low, high) from exc


def _from_storage(setting: Setting, stored: str | None) -> Any:
    """A stored global value, read leniently: malformed reads as the default."""
    if stored is None:
        return setting.default
    try:
        return parse(setting, stored)
    except SettingValueError:
        return setting.default


def _chat_value(setting: Setting, chat: ChatTarget) -> Any:
    if setting.key == "daily_summary_time":
        try:
            return int(chat.daily_summary_time.split(":", 1)[0])
        except ValueError:
            return 20
    value = getattr(chat, setting.key)
    return bool(value) if setting.kind is Kind.BOOL else value


async def values(repo: Repo, scope: Scope, chat: ChatTarget | None = None) -> dict[str, Any]:
    """Every setting of a scope with its current value."""
    if scope == "chat":
        assert chat is not None
        return {s.key: _chat_value(s, chat) for s in settings_of("chat")}
    return {
        s.key: _from_storage(s, await repo.get_app_setting(s.key)) for s in settings_of("global")
    }


async def set_value(
    repo: Repo,
    scope: Scope,
    key: str,
    raw: object,
    admin_id: int | None,
    *,
    chat_id: int | None = None,
) -> Any:
    """The one way either panel changes a setting: parsed, bounded, stored.
    Raises KeyError for an unknown setting, SettingValueError for a value it
    refuses."""
    setting = find(scope, key)
    value = parse(setting, raw)
    if scope == "global":
        if setting.kind is Kind.BOOL:
            stored = "1" if value else "0"
        elif setting.kind is Kind.FLOAT:
            stored = f"{value:g}"
        else:
            stored = str(value)
        await repo.set_app_setting(key, stored, admin_id)
        return value
    assert chat_id is not None
    if key == "is_active":
        await repo.set_chat_active(chat_id, value)
    elif key == "daily_summary_time":
        await repo.update_chat_settings(chat_id, daily_summary_time=f"{value:02d}:00")
    elif setting.kind is Kind.BOOL:
        await repo.update_chat_settings(chat_id, **{key: 1 if value else 0})
    else:
        await repo.update_chat_settings(chat_id, **{key: value})
    return value


# ------------------------------------------------------------------ words


# The offsets with a place named beside them where there is room for one —
# the Mini App's pickers; the bot's buttons show the offset alone.
_TZ_PLACES = (-480, -300, 0, 60, 120, 180, 240, 300, 360, 420, 480, 540, 600, 660, 720)


def value_label(setting: Setting, value: Any, *, locale: str, place: bool = False) -> str:
    """A value as both panels show it. `place` adds a city to a time zone
    ("Москва · UTC+3") where one is known — the Mini App asks for it."""

    def _(key: str, **kwargs: Any) -> str:
        return gettext("admin", key, locale=locale, **kwargs)

    if setting.kind is Kind.BOOL:
        return _("admin-yes") if value else _("admin-no")
    if setting.kind is Kind.INT and value == 0 and setting.zero_label:
        return _(setting.zero_label)
    if setting.kind is Kind.FLOAT:
        return f"{value:g}"
    if setting.kind is Kind.HOUR:
        return f"{value:02d}:00"
    if setting.kind is Kind.TZ:
        offset = utc_offset_label(int(value))
        if place and int(value) in _TZ_PLACES:
            sign = "m" if int(value) < 0 else "p"
            return f"{_(f'admin-tz-place-{sign}{abs(int(value))}')} · {offset}"
        return offset
    if setting.key == DEFAULT_RARITY_MODE_KEY:
        return gettext("keyboards", f"kb-rarity-{value}", locale=locale)
    if setting.key == "locale":
        return LOCALE_NAMES.get(str(value), str(value))
    if setting.key == "digest_threshold":
        return _("admin-digest-never") if value >= DIGEST_NEVER else str(value)
    if setting.key == post_picture.STYLE_KEY:
        return _(f"admin-post-picture-{value}")
    return str(value)


def label(setting: Setting, *, locale: str) -> str:
    return gettext("admin", setting.label, locale=locale)


def hint(setting: Setting, *, locale: str) -> str | None:
    return gettext("admin", setting.hint, locale=locale) if setting.hint else None


def group_label(scope: Scope, group: str, *, locale: str) -> str:
    return gettext("admin", f"admin-group-{scope}-{group}", locale=locale)
