"""Locale resolution (#48) — the mechanism only.

Nothing here asserts English text: bot/locales/en/ does not exist yet at
this point, and the whole point of these tests is that the seam behaves
(and keeps answering Russian) before, during, and after it is filled in.
"""

from __future__ import annotations

import pytest
from aiogram.types import Chat, User

from bot.db.repo import Repo
from bot.i18n import (
    DEFAULT_LOCALE,
    LocaleManager,
    gettext,
    normalize_locale,
    static_i18n,
    translator,
)

CHAT_ID = -100500
TG_ID = 4242


def _user(tg_id: int = TG_ID) -> User:
    return User(id=tg_id, is_bot=False, first_name="Игорь")


def _group(chat_id: int = CHAT_ID) -> Chat:
    return Chat(id=chat_id, type="supergroup")


def _private(tg_id: int = TG_ID) -> Chat:
    return Chat(id=tg_id, type="private")


# ------------------------------------------------------------ normalization


def test_normalize_locale_keeps_known_locales() -> None:
    assert normalize_locale("ru") == "ru"
    assert normalize_locale("en") == "en"


@pytest.mark.parametrize("value", [None, "", "de", "RU", "ru-RU", "en_US"])
def test_normalize_locale_coerces_anything_else(value: str | None) -> None:
    # A row written by a newer version of the bot, or hand-edited, must
    # degrade to Russian rather than raise halfway through a render.
    assert normalize_locale(value) == DEFAULT_LOCALE


# ------------------------------------------------------------------ gettext


def test_gettext_defaults_to_russian() -> None:
    assert gettext("util", "util-ago-never") == "никогда"


def test_gettext_explicit_default_locale_is_unchanged() -> None:
    assert gettext("util", "util-ago-never", locale=DEFAULT_LOCALE) == "никогда"


def test_gettext_unknown_locale_falls_back_to_russian() -> None:
    assert gettext("util", "util-ago-never", locale="de") == "никогда"


def test_gettext_passes_arguments_through() -> None:
    assert "5" in gettext("util", "util-ago-minutes", count=5)


def test_translator_binds_module_and_locale() -> None:
    _ = translator("util", "ru")
    assert _("util-ago-never") == "никогда"
    assert "5" in _("util-ago-minutes", count=5)


def test_translator_without_locale_is_russian() -> None:
    assert translator("util")("util-ago-never") == "никогда"


def test_static_i18n_carries_its_locale() -> None:
    context = static_i18n("util", "en")
    assert context.locale == "en"
    # No en/ files exist yet, so this still resolves through the fallback
    # chain to the Russian string — the seam works, the translation is just
    # not there yet.
    assert context.get("util-ago-never") == "никогда"


def test_static_i18n_bad_locale_is_normalized() -> None:
    assert static_i18n("util", "klingon").locale == DEFAULT_LOCALE


# ---------------------------------------------------------- repo accessors


async def test_chat_locale_defaults_to_russian(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    assert await repo.chat_locale(CHAT_ID) == "ru"


async def test_chat_locale_unknown_chat_is_russian(repo: Repo) -> None:
    # Called on the render path for every group message — a chat with no
    # settings row must never blow up there.
    assert await repo.chat_locale(-1) == "ru"


async def test_chat_locale_round_trips(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.update_chat_settings(CHAT_ID, locale="en")
    assert await repo.chat_locale(CHAT_ID) == "en"


async def test_user_locale_defaults_to_russian(repo: Repo) -> None:
    await repo.ensure_user(TG_ID)
    assert await repo.user_locale(TG_ID) == "ru"


async def test_user_locale_unknown_user_is_russian(repo: Repo) -> None:
    assert await repo.user_locale(-1) == "ru"


async def test_user_locale_round_trips(repo: Repo) -> None:
    await repo.ensure_user(TG_ID)
    await repo.update_user_settings(TG_ID, locale="en")
    assert await repo.user_locale(TG_ID) == "en"
    settings = await repo.get_user_settings(TG_ID)
    assert settings is not None
    assert settings.locale == "en"


async def test_update_user_settings_still_rejects_unknown_fields(repo: Repo) -> None:
    await repo.ensure_user(TG_ID)
    with pytest.raises(ValueError, match="lang"):
        await repo.update_user_settings(TG_ID, lang="en")


# --------------------------------------------------------------- the manager


async def test_manager_uses_the_chats_locale_in_a_group(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    await repo.ensure_user(TG_ID)
    await repo.update_chat_settings(CHAT_ID, locale="en")
    await repo.update_user_settings(TG_ID, locale="ru")

    manager = LocaleManager()
    # The person's own setting loses here on purpose: one group message is
    # one shared object, every member reads the same text.
    assert await manager.get_locale(repo, _group(), _user()) == "en"


async def test_manager_uses_the_persons_locale_in_a_dm(repo: Repo) -> None:
    await repo.ensure_user(TG_ID)
    await repo.update_user_settings(TG_ID, locale="en")

    manager = LocaleManager()
    assert await manager.get_locale(repo, _private(), _user()) == "en"


async def test_manager_normalizes_a_bad_stored_value(repo: Repo) -> None:
    await repo.upsert_chat(CHAT_ID, "Гейминг-чат", 1)
    # Straight past update_chat_settings' own allow-list, the way a
    # hand-edited database or an older/newer schema would look.
    await repo._conn.execute(
        "UPDATE chat_settings SET locale = 'klingon' WHERE chat_id = ?", (CHAT_ID,)
    )
    manager = LocaleManager()
    assert await manager.get_locale(repo, _group(), _user()) == DEFAULT_LOCALE


async def test_manager_without_a_repo_is_russian() -> None:
    # Defensive: an update reaching the middleware before dispatcher["repo"]
    # is set would otherwise crash every handler rather than degrade.
    assert await LocaleManager().get_locale(None, _group(), _user()) == DEFAULT_LOCALE


async def test_manager_without_a_user_or_chat_is_russian(repo: Repo) -> None:
    assert await LocaleManager().get_locale(repo, None, None) == DEFAULT_LOCALE


async def test_manager_set_locale_is_not_a_seam() -> None:
    with pytest.raises(NotImplementedError):
        await LocaleManager().set_locale("en")
