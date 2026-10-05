"""Tests for the Group Hub "🔔 Настройка уведомлений" publish button (#54).

The button cycles through publication modes (all -> rare -> hidden -> all)
instead of dead-ending after the first press, respecting admin's default_rarity_mode
on the initial subscription.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from aiogram import Bot
from aiogram.types import CallbackQuery, Chat, Message
from aiogram.types import User as TgUser
from aiogram_i18n import I18nContext

from bot.config import Settings
from bot.constants import RarityMode
from bot.db.repo import Repo
from bot.handlers.chat import subscribe_button
from bot.i18n import static_i18n
from bot.views.chat import hub_keyboard

CHAT_ID = -100555
TG_ID = 4242


def _make_callback(chat_id: int = CHAT_ID, tg_id: int = TG_ID) -> tuple[MagicMock, MagicMock]:
    message = MagicMock(spec=Message)
    message.chat = Chat(id=chat_id, type="supergroup", title="Gamers Chat")
    message.edit_text = AsyncMock()
    message.answer = AsyncMock()

    callback = MagicMock(spec=CallbackQuery)
    callback.data = "sub:on"
    callback.from_user = TgUser(id=tg_id, is_bot=False, first_name="Tester")
    callback.message = message
    callback.answer = AsyncMock()
    return callback, message


def _make_bot() -> MagicMock:
    bot = MagicMock(spec=Bot)
    me_user = TgUser(id=999, is_bot=True, first_name="Bot", username="xboxbot")
    bot.me = AsyncMock(return_value=me_user)
    return bot


def test_hub_keyboard_publish_button_label_ru() -> None:
    markup = hub_keyboard("xboxbot", CHAT_ID)
    buttons = [b for row in markup.inline_keyboard for b in row]
    publish_btn = next(b for b in buttons if b.callback_data == "sub:on")
    assert publish_btn.text == "🔔 Настройка уведомлений"


def test_hub_keyboard_publish_button_label_en() -> None:
    i18n_en = static_i18n("chat", "en")
    markup = hub_keyboard("xboxbot", CHAT_ID, i18n_en)
    buttons = [b for row in markup.inline_keyboard for b in row]
    publish_btn = next(b for b in buttons if b.callback_data == "sub:on")
    assert publish_btn.text == "🔔 Notification settings"


async def test_subscribe_button_redirects_when_not_connected(
    repo: Repo, i18n: I18nContext, settings: Settings
) -> None:
    callback, message = _make_callback()
    bot = _make_bot()

    await subscribe_button(callback, repo, bot, i18n, settings)

    assert not await repo.is_subscribed(CHAT_ID, TG_ID)
    callback.answer.assert_called_once_with(url=f"https://t.me/xboxbot?start=connect{CHAT_ID}")
    message.answer.assert_called_once()
    assert i18n.get("chat-subscribe-connect-first") in message.answer.call_args[0][0]


async def test_subscribe_button_first_press_subscribes_with_admin_default_all(
    repo: Repo, i18n: I18nContext, settings: Settings
) -> None:
    await repo.ensure_user(TG_ID, "tester")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Gamertag1", 0)
    callback, message = _make_callback()
    bot = _make_bot()

    await subscribe_button(callback, repo, bot, i18n, settings)

    assert await repo.is_subscribed(CHAT_ID, TG_ID)
    assert await _mode(repo) == RarityMode.ALL
    callback.answer.assert_called_once_with("Публикую все достижения")
    message.edit_text.assert_called_once()


async def test_subscribe_button_first_press_subscribes_with_admin_default_rare(
    repo: Repo, i18n: I18nContext, settings: Settings
) -> None:
    await repo.set_app_setting("default_rarity_mode", RarityMode.RARE)
    await repo.ensure_user(TG_ID, "tester")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Gamertag1", 0)
    callback, _ = _make_callback()
    bot = _make_bot()

    await subscribe_button(callback, repo, bot, i18n, settings)

    assert await repo.is_subscribed(CHAT_ID, TG_ID)
    assert await _mode(repo) == RarityMode.RARE
    callback.answer.assert_called_once_with("Только редкие")


async def test_subscribe_button_cycles_all_rare_hidden_all(
    repo: Repo, i18n: I18nContext, settings: Settings
) -> None:
    await repo.ensure_user(TG_ID, "tester")
    await repo.link_xbox_account(TG_ID, "xuid-1", "Gamertag1", 0)
    bot = _make_bot()

    # 1. Initial subscription -> ALL
    callback1, _ = _make_callback()
    await subscribe_button(callback1, repo, bot, i18n, settings)
    assert await _mode(repo) == RarityMode.ALL
    callback1.answer.assert_called_once_with("Публикую все достижения")
    subs1 = await repo.chat_subscribers(CHAT_ID)
    assert any(s.tg_id == TG_ID for s in subs1)

    # 2. Press again -> RARE
    callback2, _ = _make_callback()
    await subscribe_button(callback2, repo, bot, i18n, settings)
    assert await _mode(repo) == RarityMode.RARE
    callback2.answer.assert_called_once_with("Только редкие")
    subs2 = await repo.chat_subscribers(CHAT_ID)
    assert any(s.tg_id == TG_ID for s in subs2)

    # 3. Press again -> HIDDEN
    callback3, _ = _make_callback()
    await subscribe_button(callback3, repo, bot, i18n, settings)
    assert await _mode(repo) == RarityMode.HIDDEN
    callback3.answer.assert_called_once_with("Ничего не публикую")
    subs3 = await repo.chat_subscribers(CHAT_ID)
    assert not any(s.tg_id == TG_ID for s in subs3)  # Excluded from hub publishing roster!

    # 4. Press again -> ALL
    callback4, _ = _make_callback()
    await subscribe_button(callback4, repo, bot, i18n, settings)
    assert await _mode(repo) == RarityMode.ALL
    callback4.answer.assert_called_once_with("Публикую все достижения")
    subs4 = await repo.chat_subscribers(CHAT_ID)
    assert any(s.tg_id == TG_ID for s in subs4)  # Back in roster!


async def test_the_mode_outlives_a_subscription(repo: Repo) -> None:
    """The mode is the person's since #126: unsubscribing from one chat
    leaves it as it was for every other."""
    await repo.upsert_chat(CHAT_ID, "Chat", 1)
    await repo.ensure_user(TG_ID, "tester")
    await repo.subscribe(CHAT_ID, TG_ID)
    await repo.update_user_settings(TG_ID, rarity_mode=RarityMode.RARE)
    await repo.unsubscribe(CHAT_ID, TG_ID)
    assert await _mode(repo) == RarityMode.RARE


async def _mode(repo: Repo) -> str:
    settings_row = await repo.get_user_settings(TG_ID)
    assert settings_row is not None
    return settings_row.rarity_mode
