"""The profile-photo sweep (2026-09-13, owner request — the mini-app shows
people). What is stored is Telegram's own file_id, never an image and never a
URL; the Bot is faked at the API boundary, like every other poller test here.
"""

from __future__ import annotations

from types import SimpleNamespace

from bot.db.repo import Repo
from bot.poller.avatars import AvatarRefresh


class _FakeBot:
    """`get_user_profile_photos` as aiogram returns it: one photo, every size
    of it, smallest first."""

    def __init__(self, by_user: dict[int, list[tuple[str, str]]] | None = None) -> None:
        self.by_user = by_user or {}
        self.asked: list[int] = []

    async def get_user_profile_photos(self, tg_id: int, limit: int = 1) -> SimpleNamespace:
        self.asked.append(tg_id)
        sizes = self.by_user.get(tg_id, [])
        photos = [[SimpleNamespace(file_id=f, file_unique_id=u) for f, u in sizes]] if sizes else []
        return SimpleNamespace(photos=photos)


async def test_the_largest_size_is_what_gets_stored(repo: Repo) -> None:
    await repo.ensure_user(1, "someone")
    bot = _FakeBot({1: [("small", "u1"), ("big", "u1")]})

    await AvatarRefresh(bot, repo).tick()  # type: ignore[arg-type]

    user = await repo.get_user(1)
    assert user is not None and user.photo_file_id == "big"


async def test_somebody_with_no_visible_photo_is_not_asked_again_next_tick(repo: Repo) -> None:
    """A private profile answers with nothing. The check is still stamped, or
    this person would be first in line on every tick forever."""
    await repo.ensure_user(1, "someone")
    bot = _FakeBot()

    await AvatarRefresh(bot, repo).tick()  # type: ignore[arg-type]
    await AvatarRefresh(bot, repo).tick()  # type: ignore[arg-type]

    assert bot.asked == [1]
    user = await repo.get_user(1)
    assert user is not None and user.photo_file_id is None


async def test_a_failure_leaves_the_person_first_in_line(repo: Repo) -> None:
    """One person must never end a tick, and an unanswered check must not
    count as an answer."""
    await repo.ensure_user(1, "someone")

    class _Boom(_FakeBot):
        async def get_user_profile_photos(self, tg_id: int, limit: int = 1):
            self.asked.append(tg_id)
            raise RuntimeError("telegram said no")

    bot = _Boom()
    await AvatarRefresh(bot, repo).tick()  # type: ignore[arg-type]
    await AvatarRefresh(bot, repo).tick()  # type: ignore[arg-type]

    assert bot.asked == [1, 1]


async def test_a_tick_takes_only_its_own_bite(repo: Repo) -> None:
    for tg_id in range(1, 6):
        await repo.ensure_user(tg_id, f"user{tg_id}")
    bot = _FakeBot({tg_id: [("f", "u")] for tg_id in range(1, 6)})

    await AvatarRefresh(bot, repo, users_per_tick=2).tick()  # type: ignore[arg-type]

    assert len(bot.asked) == 2
