"""i18n wiring (2026-09-07) — aiogram_i18n + Fluent, the native localization
middleware for aiogram 3.

Two locales ship: "ru" (the default, and the fallback for every key) and
"en" (#48). Which one an update renders in is decided per *context*, not per
process, by `LocaleManager` below: a group always follows its own
`chat_settings.locale` (Telegram cannot show two viewers of the same group
message different text, so a chat needs one shared answer, set by an admin),
a DM follows the person's own `user_settings.locale`.

Two seams exist because not everything runs inside aiogram's own update
handling:

* Handlers get an `I18nContext` injected by `I18nMiddleware`, already bound
  to the right locale — they just call `i18n.get(...)` and never think about
  it.
* Pollers, notifiers and other non-DI code call `gettext(module, key,
  locale=...)`, or bind the locale once via `translator(module, locale)` and
  call the result. The locale is always an explicit argument there: the
  publisher and the daily summary both loop over chats, and a context
  variable that someone forgot to set would silently render one chat's
  message in another chat's language.

A key missing from "en" falls back to "ru" rather than raising, on both
seams (`locales_map` on the core, Fluent's own locale chain in `gettext`) —
so `bot/locales/en/` can be filled in file by file without a half-translated
locale ever breaking a screen.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiogram_i18n import I18nContext, I18nMiddleware
from aiogram_i18n.cores.fluent_runtime_core import FluentRuntimeCore
from aiogram_i18n.managers import BaseManager, ConstManager
from fluent.runtime import FluentLocalization, FluentResourceLoader

if TYPE_CHECKING:
    from aiogram.types import Chat, User

    from bot.db.repo import Repo

DEFAULT_LOCALE = "ru"
LOCALES_DIR = Path(__file__).parent / "locales"

#: Every locale a chat or a person may actually be set to. The UI offers
#: exactly these; anything else found in the database (a hand-edited row, a
#: locale removed in a later version) is coerced back to DEFAULT_LOCALE by
#: `normalize_locale` rather than crashing a render.
AVAILABLE_LOCALES = ("ru", "en")

#: Per-key fallback for the core: a key present in ru but not yet in en
#: resolves to the Russian one instead of raising KeyNotFoundError. This is
#: what lets bot/locales/en/ be translated incrementally.
LOCALES_MAP = {locale: DEFAULT_LOCALE for locale in AVAILABLE_LOCALES if locale != DEFAULT_LOCALE}


def normalize_locale(locale: str | None) -> str:
    """Coerce a stored/incoming locale to one this bot actually has files
    for. Callers pass database values straight in — a row written by an
    older or newer version of the bot must degrade to Russian, never raise
    in the middle of rendering a message."""
    return locale if locale in AVAILABLE_LOCALES else DEFAULT_LOCALE


class StaticI18nContext:
    """Small synchronous context for service helpers and legacy unit callers."""

    def __init__(self, module: str, locale: str = DEFAULT_LOCALE) -> None:
        self._module = module
        self._locale = normalize_locale(locale)

    @property
    def locale(self) -> str:
        return self._locale

    def get(self, key: str, **kwargs: Any) -> str:
        value = gettext(self._module, key, locale=self._locale, **kwargs)
        if value != key:
            return value
        for path in LOCALES_DIR.joinpath(DEFAULT_LOCALE, "LC_MESSAGES").glob("*.ftl"):
            module = path.stem
            if module == self._module:
                continue
            value = gettext(module, key, locale=self._locale, **kwargs)
            if value != key:
                return value
        return value


def static_i18n(module: str, locale: str = DEFAULT_LOCALE) -> StaticI18nContext:
    return StaticI18nContext(module, locale)


class LocaleManager(BaseManager):
    """Picks the locale for one update: the chat's own setting in a group,
    the person's own in a DM (#48).

    Both parameters below are filled in by aiogram's own DI — `event_chat`
    and `event_from_user` come from aiogram itself, `repo` from
    `dispatcher["repo"]` in main.py. A missing row or an unreadable value
    resolves to Russian, the same answer this bot gave before locales
    existed at all.
    """

    def __init__(self, default_locale: str = DEFAULT_LOCALE) -> None:
        super().__init__(default_locale=default_locale)

    async def get_locale(
        self,
        repo: Repo | None = None,
        event_chat: Chat | None = None,
        event_from_user: User | None = None,
    ) -> str:
        if repo is None:
            return DEFAULT_LOCALE
        # A group's own setting wins over any individual's: the message is
        # one shared object every member reads.
        if event_chat is not None and event_chat.type != "private":
            return normalize_locale(await repo.chat_locale(event_chat.id))
        if event_from_user is not None:
            return normalize_locale(await repo.user_locale(event_from_user.id))
        return DEFAULT_LOCALE

    async def set_locale(self, locale: str, **kwargs: Any) -> None:
        # Locale changes go through the panel/admin handlers, which write the
        # setting (and re-render their own screen) via the repo directly —
        # there is no flow where aiogram_i18n's own setter is the right seam,
        # same as ConstManager's own stance.
        raise NotImplementedError


def _core() -> FluentRuntimeCore:
    return FluentRuntimeCore(
        path=LOCALES_DIR / "{locale}" / "LC_MESSAGES",
        default_locale=DEFAULT_LOCALE,
        locales_map=LOCALES_MAP,
    )


def build_i18n_middleware() -> I18nMiddleware:
    return I18nMiddleware(
        core=_core(),
        manager=LocaleManager(DEFAULT_LOCALE),
        default_locale=DEFAULT_LOCALE,
    )


async def build_i18n_context(locale: str = DEFAULT_LOCALE) -> I18nContext:
    """A standalone I18nContext for the rare bit of non-handler code (e.g.
    main.py's on_linked callback) that calls into bot/handlers/keyboards.py
    — those functions expect a real I18nContext (they call i18n.get(...)
    same as any handler), not the plain-string gettext() below. The caller
    passes the locale it already resolved for its own target; ConstManager
    is right *here* specifically because this context is built for one known
    person and then thrown away, never reused across targets."""
    locale = normalize_locale(locale)
    core = _core()
    await core.startup()
    return I18nContext(locale=locale, core=core, manager=ConstManager(locale), data={})


@cache
def _localization(module: str, locale: str) -> FluentLocalization:
    # A module-scoped instance rather than one loader for everything: each
    # .ftl file only needs its own module's keys in scope, same as
    # I18nContext.get() only ever resolves against the middleware's single
    # merged core — this mirrors that per-call lookup without needing one.
    #
    # The locale chain ends in DEFAULT_LOCALE so a key not yet translated
    # into `locale` falls back to the Russian one, matching LOCALES_MAP on
    # the core seam above.
    loader = FluentResourceLoader(str(LOCALES_DIR / "{locale}" / "LC_MESSAGES"))
    chain = [locale] if locale == DEFAULT_LOCALE else [locale, DEFAULT_LOCALE]
    return FluentLocalization(chain, [f"{module}.ftl"], loader)


def gettext(module: str, key: str, locale: str | None = None, **kwargs: Any) -> str:
    """Synchronous translation for code that runs outside aiogram's own
    update handling — schedulers (poller/*), notifiers (services/notify.py),
    and anything else with no I18nContext to be injected into in the first
    place. Handlers keep using I18nContext via DI as before; this is only
    for the non-DI case.

    `locale` is explicit rather than ambient on purpose: the publisher and
    the daily summary both render for many chats in one loop, so a locale
    carried in module or context state would be exactly the kind of thing
    that renders one chat's message in another chat's language after an
    early `continue`. Callers that genuinely have no target (startup command
    descriptions, a crash message before any chat is known) omit it and get
    Russian.
    """
    return _localization(module, normalize_locale(locale)).format_value(key, kwargs or None)


def translator(module: str, locale: str | None = None) -> Callable[..., str]:
    """`gettext` with the module and locale bound once, for the many call
    sites that render a whole screen for one known target: `_ =
    translator("daily", locale)` at the top of the function, then `_("key",
    count=n)` throughout, exactly like the module-level shorthand these
    replaced — except the locale travels with it."""
    resolved = normalize_locale(locale)
    return lambda key, **kwargs: gettext(module, key, locale=resolved, **kwargs)
