"""Send test achievement notification, test digest, and test promo message to the test admin.

Usage:
    python -m scripts.send_test_notifications
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import get_settings
from bot.constants import Platform
from bot.db.repo import AchievementRow
from bot.i18n import gettext
from bot.services.mini_app import mini_app_open_markup
from bot.util import utcnow
from bot.views.notification import format_digest, format_single
from bot.views.promo import promo_keyboard, promo_text

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test_notifications")


async def main() -> None:
    settings = get_settings()
    if not settings.admin_tg_ids:
        log.error("No admin_tg_ids configured in settings/env.")
        return

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(link_preview_is_disabled=True),
    )
    try:
        me = await bot.me()
        bot_username = (me.username or "").lstrip("@")
        log.info("Connected to bot @%s", bot_username)

        for admin_id in settings.admin_tg_ids:
            log.info("Sending test notifications to admin %s...", admin_id)
            locale = "ru"

            # 1. Single achievement notification
            sample_item = AchievementRow(
                platform=Platform.XBOX_MODERN,
                title_id="test_game_1",
                achievement_id="test_ach_1",
                name="Master of the Universe",
                description="Complete all challenges on Heroic difficulty.",
                gamerscore=50,
                rarity_percent=4.2,
                icon_url="https://images-eds-ssl.xboxlive.com/image?url=27S1DHqE.cHkmFg4nspsd20onq.a6RlSrPILfpIfgG69B6hv5oeObwDwTlW9DupHdRgbFrKl5Sc.TjixYquVchOcOmI_rTy9ypV5EspEr2cKX4NCAPgRf0qys0L0kJccFLpG92BAO_pXyKPkAGEY.QCBnhqZIkuW5fUb5izjBb4-",
                is_secret=False,
                unlocked_at=utcnow().isoformat(),
                title_name="Halo Infinite",
            )
            single_text = format_single("PlayerOne", sample_item, "Halo Infinite", locale=locale)
            btn_text = gettext("chat", "chat-open-mini-app", locale=locale)
            single_markup = mini_app_open_markup(
                btn_text,
                https_url=settings.mini_app_url or "",
                bot_username=bot_username,
                chat_id=admin_id,
                in_group=False,
            )
            try:
                await bot.send_photo(
                    admin_id,
                    photo=sample_item.icon_url,
                    caption=single_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=single_markup,
                )
                log.info("Sent single achievement notification.")
            except Exception as exc:
                log.warning("send_photo failed (%s), falling back to text", exc)
                await bot.send_message(
                    admin_id,
                    single_text,
                    parse_mode=ParseMode.HTML,
                    reply_markup=single_markup,
                )

            # 2. Digest notification
            sample_digest_items = [
                sample_item,
                AchievementRow(
                    platform=Platform.XBOX_MODERN,
                    title_id="test_game_1",
                    achievement_id="test_ach_2",
                    name="Brothers in Arms",
                    description="Win a co-op match.",
                    gamerscore=25,
                    rarity_percent=12.5,
                    icon_url="https://images.unsplash.com/photo-1612287233207-6f8b960b77b7?w=500",
                    is_secret=False,
                    unlocked_at=utcnow().isoformat(),
                    title_name="Halo Infinite",
                ),
            ]
            digest_text = format_digest(
                "PlayerOne", "Halo Infinite", sample_digest_items, locale=locale
            )
            digest_markup = mini_app_open_markup(
                btn_text,
                https_url=settings.mini_app_url or "",
                bot_username=bot_username,
                chat_id=admin_id,
                in_group=False,
            )
            await bot.send_message(
                admin_id,
                digest_text,
                parse_mode=ParseMode.HTML,
                reply_markup=digest_markup,
            )
            log.info("Sent digest notification.")

            # 3. Pinned promo message
            p_markup = promo_keyboard(
                bot_username,
                admin_id,
                mini_app_url=settings.mini_app_url or "",
                is_group=False,
                locale=locale,
            )
            await bot.send_message(
                admin_id,
                promo_text(locale=locale),
                parse_mode=ParseMode.HTML,
                reply_markup=p_markup,
            )
            log.info("Sent pinned promo message.")
            log.info("All test notifications successfully sent to admin %s!", admin_id)

    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
