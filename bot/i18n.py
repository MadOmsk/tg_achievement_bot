"""i18n wiring (2026-09-07) — aiogram_i18n + Fluent, the native localization
middleware for aiogram 3.

Only "ru" ships today — every user-facing string in this bot is Russian by
design (CLAUDE.md), and that does not change here. This module exists so
migrating a handler's hardcoded f-strings into bot/locales/*.ftl can happen
incrementally (one handler at a time, as it's touched anyway) instead of a
single big-bang rewrite: DEFAULT_LOCALE plus ConstManager means every
update resolves to "ru" regardless of a user's own Telegram language, so
today's behavior (always Russian) is unchanged even while some handlers
still build plain f-strings and others start pulling from `i18n.get(...)`.

Adding a second language later only means dropping a new
bot/locales/<code>/LC_MESSAGES/bot.ftl next to this one and switching the
manager — no changes needed in any handler that already uses I18nContext.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Any

from aiogram_i18n import I18nContext, I18nMiddleware
from aiogram_i18n.cores.fluent_runtime_core import FluentRuntimeCore
from aiogram_i18n.managers import ConstManager
from fluent.runtime import FluentLocalization, FluentResourceLoader

DEFAULT_LOCALE = "ru"
LOCALES_DIR = Path(__file__).parent / "locales"


class StaticI18nContext:
    """Small synchronous context for service helpers and legacy unit callers."""

    def __init__(self, module: str) -> None:
        self._module = module

    def get(self, key: str, **kwargs: Any) -> str:
        value = gettext(self._module, key, **kwargs)
        if value != key:
            return value
        for path in LOCALES_DIR.joinpath(DEFAULT_LOCALE, "LC_MESSAGES").glob("*.ftl"):
            module = path.stem
            if module == self._module:
                continue
            value = gettext(module, key, **kwargs)
            if value != key:
                return value
        return value


def static_i18n(module: str) -> StaticI18nContext:
    return StaticI18nContext(module)


def _core() -> FluentRuntimeCore:
    return FluentRuntimeCore(path=LOCALES_DIR / "{locale}" / "LC_MESSAGES")


def build_i18n_middleware() -> I18nMiddleware:
    return I18nMiddleware(
        core=_core(),
        manager=ConstManager(DEFAULT_LOCALE),
        default_locale=DEFAULT_LOCALE,
    )


async def build_i18n_context() -> I18nContext:
    """A standalone I18nContext for the rare bit of non-handler code (e.g.
    main.py's on_linked callback) that calls into bot/handlers/keyboards.py
    — those functions expect a real I18nContext (they call i18n.get(...)
    same as any handler), not the plain-string gettext() above. Building one
    directly is cheap and safe here: ConstManager always resolves "ru", so
    there's no per-user state this could get wrong."""
    core = _core()
    await core.startup()
    return I18nContext(
        locale=DEFAULT_LOCALE, core=core, manager=ConstManager(DEFAULT_LOCALE), data={}
    )


@cache
def _localization(module: str) -> FluentLocalization:
    # A module-scoped instance rather than one loader for everything: each
    # .ftl file only needs its own module's keys in scope, same as
    # I18nContext.get() only ever resolves against the middleware's single
    # merged core — this mirrors that per-call lookup without needing one.
    loader = FluentResourceLoader(str(LOCALES_DIR / "{locale}" / "LC_MESSAGES"))
    return FluentLocalization([DEFAULT_LOCALE], [f"{module}.ftl"], loader)


def gettext(module: str, key: str, **kwargs: Any) -> str:
    """Synchronous translation for code that runs outside aiogram's own
    update handling — schedulers (poller/*), notifiers (services/notify.py),
    and anything else with no I18nContext to be injected into in the first
    place. Handlers keep using I18nContext via DI as before; this is only
    for the non-DI case, and only ever resolves "ru" (ConstManager("ru") is
    the only locale that exists today, so there is nothing to select here).
    """
    return _localization(module).format_value(key, kwargs or None)
