"""A tg_id is an identifier, not a quantity: Fluent groups a *number*'s
digits ("188 022 193"), so every message that shows one passes it as a
string. This pins the places that used to pass the int."""

from __future__ import annotations

from bot.db.repo import Repo
from bot.services.admin_actions import AdminContext, Confirm, Target, perform
from bot.services.notify import SuperadminNotifier

TG_ID = 188022193


async def test_delete_confirmations_show_the_id_in_one_piece(repo: Repo, settings) -> None:
    person = await repo.ensure_user(TG_ID, "igor")
    ctx = AdminContext(repo, settings)
    for locale in ("ru", "en"):
        for step in (0, 1):
            asked = await perform(ctx, "user", Target(person=person), "delete", step, locale=locale)
            assert isinstance(asked, Confirm)
            assert str(TG_ID) in asked.text, asked.text


async def test_admin_notice_shows_the_id_in_one_piece(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    notifier = SuperadminNotifier(bot=None, repo=repo, admin_ids=[])  # type: ignore[arg-type]
    for locale in ("ru", "en"):
        assert str(TG_ID) in await notifier._who(await repo.person_id(TG_ID), locale)
