"""A tg_id is an identifier, not a quantity: Fluent groups a *number*'s
digits ("188 022 193"), so every message that shows one passes it as a
string. This pins the places that used to pass the int."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.notify import SuperadminNotifier
from bot.views.admin import (
    render_admin_user_delete_confirm_1,
    render_admin_user_delete_confirm_2,
)

TG_ID = 188022193


def test_delete_confirmations_show_the_id_in_one_piece() -> None:
    for render in (render_admin_user_delete_confirm_1, render_admin_user_delete_confirm_2):
        for locale in ("ru", "en"):
            text = render("Igor", 1, TG_ID, locale=locale).text
            assert str(TG_ID) in text, text


async def test_admin_notice_shows_the_id_in_one_piece(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    notifier = SuperadminNotifier(bot=None, repo=repo, admin_ids=[])  # type: ignore[arg-type]
    for locale in ("ru", "en"):
        assert str(TG_ID) in await notifier._who(await repo.person_id(TG_ID), locale)
