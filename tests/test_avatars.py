"""The profile-photo sweep (2026-09-13, owner request — the mini-app shows
people). What is stored is Telegram's own file_id, never an image and never a
URL; the Bot is faked at the API boundary, like every other poller test here.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

from bot.db.repo import Repo
from bot.poller import avatars as avatars_poller
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


# ---- the pictures themselves, and the platform half (#55) ----


class _DownloadingBot(_FakeBot):
    """The same fake, plus `download` — aiogram hands back a file-like."""

    def __init__(self, by_user, payload: bytes = b"\xff\xd8jpeg") -> None:
        super().__init__(by_user)
        self.payload = payload
        self.downloaded: list[str] = []

    async def download(self, file_id: str):
        self.downloaded.append(file_id)
        return io.BytesIO(self.payload)


async def test_a_telegram_photo_is_downloaded_and_its_path_stored(
    repo: Repo, tmp_path, monkeypatch
) -> None:
    """#55: a file_id is only usable with the bot token, so the mini-app
    would have to round-trip getFile on every render. The bytes are kept."""
    await repo.ensure_user(1, "someone")
    bot = _DownloadingBot({1: [("small", "u1"), ("big", "u1")]})
    _use_tmp_avatar_dir(monkeypatch, tmp_path)

    await AvatarRefresh(bot, repo).tick()  # type: ignore[arg-type]

    unique_id, path = await repo.user_photo(1)
    assert (unique_id, path) == ("u1", "tg-1.jpg")
    assert (tmp_path / "data" / "avatars" / "tg-1.jpg").read_bytes() == b"\xff\xd8jpeg"
    assert bot.downloaded == ["big"]


async def test_the_same_photo_is_not_downloaded_twice(repo: Repo, tmp_path, monkeypatch) -> None:
    """The common case by far. `file_unique_id` is stable per photo, so
    "still the same face" costs one comparison and no traffic."""
    await repo.ensure_user(1, "someone")
    bot = _DownloadingBot({1: [("big", "u1")]})
    _use_tmp_avatar_dir(monkeypatch, tmp_path)
    await AvatarRefresh(bot, repo).tick()  # type: ignore[arg-type]
    await repo.set_user_photo(1, "big", "u1")  # reset the clock, same photo

    await AvatarRefresh(bot, repo).refresh_now(1)  # type: ignore[arg-type]

    assert bot.downloaded == ["big"]


async def test_a_platform_account_gets_its_own_picture(repo: Repo, tmp_path, monkeypatch) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "Gabe")
    _use_tmp_avatar_dir(monkeypatch, tmp_path)

    async def fake_avatar_url(api_key: str, steam_id: str) -> str:
        return "https://avatars.steamstatic.com/abc_full.jpg"

    downloaded: list[tuple[str, str]] = []

    async def fake_download(url: str, name: str, *, root=None):
        downloaded.append((url, name))
        return name, "hash-of-the-bytes"

    monkeypatch.setattr(avatars_poller, "steam_avatar_url", fake_avatar_url)
    monkeypatch.setattr(avatars_poller.avatars, "download", fake_download)
    steam_auth = SimpleNamespace(get_key=_returning("a-key"))

    await AvatarRefresh(_FakeBot(), repo, steam_auth=steam_auth).tick()  # type: ignore[arg-type]

    url, stored_hash = await repo.account_avatar("steam", "76561197960287930")
    assert url == "https://avatars.steamstatic.com/abc_full.jpg"
    assert stored_hash == "hash-of-the-bytes"
    assert downloaded == [(url, "steam-76561197960287930.jpg")]


async def test_an_unchanged_platform_picture_is_not_downloaded_again(
    repo: Repo, tmp_path, monkeypatch
) -> None:
    await repo.ensure_user(1, "someone")
    await repo.link_platform_account(1, "steam", "76561197960287930", "Gabe")
    await repo.set_account_avatar("steam", "76561197960287930", "https://a/full.jpg", "f.jpg", "h")
    _use_tmp_avatar_dir(monkeypatch, tmp_path)

    async def fake_avatar_url(api_key: str, steam_id: str) -> str:
        return "https://a/full.jpg"

    async def fail_download(url: str, name: str, *, root=None):
        raise AssertionError("should not download an unchanged picture")

    monkeypatch.setattr(avatars_poller, "steam_avatar_url", fake_avatar_url)
    monkeypatch.setattr(avatars_poller.avatars, "download", fail_download)
    steam_auth = SimpleNamespace(get_key=_returning("a-key"))

    await AvatarRefresh(_FakeBot(), repo, steam_auth=steam_auth).tick()  # type: ignore[arg-type]

    assert await repo.account_avatar("steam", "76561197960287930") == ("https://a/full.jpg", "h")


def _use_tmp_avatar_dir(monkeypatch, tmp_path) -> None:
    """services/avatars.py writes under the working directory — each test
    gets its own, undone afterwards, so nothing lands in the repository and
    no other test inherits the change."""
    monkeypatch.chdir(tmp_path)


def _returning(value):
    async def answer():
        return value

    return answer
