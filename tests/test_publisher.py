"""poller/publisher.py's gallery building (SPEC 7.1/7.2)."""

from __future__ import annotations

import base64

from bot.db.repo import AchievementRow
from bot.poller.publisher import _gallery


def achievement(
    achievement_id: str,
    icon_url: str | None,
    is_secret: bool = False,
) -> AchievementRow:
    return AchievementRow(
        title_id="1",
        achievement_id=achievement_id,
        name="Ashes to Ashes",
        description=None,
        icon_url=icon_url,
        unlocked_at="2026-09-02T10:00:00+00:00",
        gamerscore=10,
        rarity_percent=None,
        platform="xbox_360",
        is_secret=is_secret,
    )


def test_gallery_has_one_entry_per_achievement_with_distinct_icons() -> None:
    items = [achievement("a1", "url1"), achievement("a2", "url2")]
    assert _gallery(items) == [("url1", False), ("url2", False)]


def test_gallery_collapses_a_shared_icon_to_one_entry() -> None:
    """Xbox 360 achievements all share the game's own box art — a digest of
    several must not repeat that one picture once per achievement."""
    items = [achievement("a1", "boxart"), achievement("a2", "boxart"), achievement("a3", "boxart")]
    assert _gallery(items) == [("boxart", False)]


def test_gallery_skips_achievements_with_no_icon() -> None:
    items = [achievement("a1", None), achievement("a2", "url")]
    assert _gallery(items) == [("url", False)]


def test_gallery_is_empty_when_nothing_has_an_icon() -> None:
    assert _gallery([achievement("a1", None)]) == []


def test_gallery_marks_a_shared_icon_as_spoiler_if_any_sharer_is_secret() -> None:
    """A secret achievement sharing an already-seen icon must not ride in
    unmarked behind an earlier public one."""
    items = [
        achievement("a1", "boxart", is_secret=False),
        achievement("a2", "boxart", is_secret=True),
    ]
    assert _gallery(items) == [("boxart", True)]


async def _gone_chat_publisher(repo, monkeypatch, *, test_bot: bool):
    """A Publisher whose only chat answers "chat not found"."""
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import SendMessage

    from bot.poller import publisher as publisher_module
    from bot.poller.publisher import Publisher, PublishJob

    chat_id = -1005001
    await repo.upsert_chat(chat_id, "Production Chat", None)
    monkeypatch.setattr(publisher_module, "is_test", lambda: test_bot)

    pub = Publisher(bot=None, repo=repo)  # type: ignore[arg-type]

    async def gone(job: PublishJob) -> int:
        raise TelegramBadRequest(
            method=SendMessage(chat_id=chat_id, text="x"), message="Bad Request: chat not found"
        )

    monkeypatch.setattr(pub, "_deliver", gone)
    await pub._send(PublishJob(chat_id=chat_id, text="x"))
    cursor = await repo._conn.execute("SELECT is_active FROM chats WHERE chat_id = ?", (chat_id,))
    return pub, chat_id, (await cursor.fetchone())["is_active"]


async def test_a_gone_chat_is_deactivated_by_the_production_bot(repo, monkeypatch) -> None:
    _, _, active = await _gone_chat_publisher(repo, monkeypatch, test_bot=False)
    assert active == 0


async def test_a_test_bot_skips_an_unreachable_chat_and_leaves_it_active(repo, monkeypatch) -> None:
    """A test bot on a copy of production's database is not a member of those
    chats; switching them off would empty the copy's chat list and Mini App."""
    pub, chat_id, active = await _gone_chat_publisher(repo, monkeypatch, test_bot=True)
    assert active == 1
    assert chat_id in pub._unreachable


async def test_publisher_attaches_mini_app_markup_to_single_achievement(repo) -> None:
    from types import SimpleNamespace

    from bot.poller.publisher import Publisher

    chat_id = -100999
    tg_id = 9999
    await repo.ensure_user(tg_id)
    await repo.upsert_chat(chat_id, "Test Chat", tg_id)
    await repo.subscribe(chat_id, await repo.person_id(tg_id))

    settings = SimpleNamespace(mini_app_url="https://app.example.com")
    pub = Publisher(bot=None, repo=repo, settings=settings, bot_username="testbot")

    item = achievement("ach1", "icon.png")
    await pub.publish(
        await repo.person_id(tg_id), "xuid1", "Player", [item], title_name="Game Title"
    )

    job = await pub._queue.get()
    assert job.chat_id == chat_id
    assert job.reply_markup is not None
    button = job.reply_markup.inline_keyboard[0][0]
    assert button.text == "Открыть Mini App"
    encoded_game = (
        base64.urlsafe_b64encode(f"{item.platform}:{item.title_id}".encode()).decode().rstrip("=")
    )
    person = await repo.person_id(tg_id)
    assert button.url == f"https://t.me/testbot?startapp=c{chat_id}p{person}g{encoded_game}"


async def test_publisher_attaches_mini_app_markup_to_digest(repo) -> None:
    from types import SimpleNamespace

    from bot.poller.publisher import Publisher

    chat_id = -100999
    tg_id = 9999
    await repo.ensure_user(tg_id)
    await repo.upsert_chat(chat_id, "Test Chat", tg_id)
    await repo.subscribe(chat_id, await repo.person_id(tg_id))
    await repo.update_chat_settings(chat_id, digest_threshold=2)  # the chat's since #126

    settings = SimpleNamespace(mini_app_url="https://app.example.com")
    pub = Publisher(bot=None, repo=repo, settings=settings, bot_username="testbot")

    items = [achievement("ach1", "icon1.png"), achievement("ach2", "icon2.png")]
    await pub.publish(
        await repo.person_id(tg_id), "xuid1", "Player", items, title_name="Game Title"
    )

    job = await pub._queue.get()
    assert job.chat_id == chat_id
    assert job.reply_markup is not None
    button = job.reply_markup.inline_keyboard[0][0]
    assert button.text == "Открыть Mini App"
    encoded_game = (
        base64.urlsafe_b64encode(f"{items[0].platform}:{items[0].title_id}".encode())
        .decode()
        .rstrip("=")
    )
    person = await repo.person_id(tg_id)
    assert button.url == f"https://t.me/testbot?startapp=c{chat_id}p{person}g{encoded_game}"


async def test_publisher_no_markup_when_no_mini_app_url(repo) -> None:
    from bot.poller.publisher import Publisher

    chat_id = -100999
    tg_id = 9999
    await repo.ensure_user(tg_id)
    await repo.upsert_chat(chat_id, "Test Chat", tg_id)
    await repo.subscribe(chat_id, await repo.person_id(tg_id))

    pub = Publisher(bot=None, repo=repo, settings=None, bot_username="testbot")

    item = achievement("ach1", "icon.png")
    await pub.publish(
        await repo.person_id(tg_id), "xuid1", "Player", [item], title_name="Game Title"
    )

    job = await pub._queue.get()
    assert job.reply_markup is None


async def test_publisher_deliver_passes_reply_markup_to_bot(repo) -> None:
    from types import SimpleNamespace

    from bot.poller.publisher import Publisher, PublishJob

    chat_id = -100999

    class _MockBot:
        def __init__(self):
            self.sent_photos = []
            self.sent_messages = []
            self.edited_markups = []

        async def send_photo(self, chat_id, photo, caption=None, reply_markup=None, **kwargs):
            self.sent_photos.append((chat_id, photo, reply_markup))
            return SimpleNamespace(message_id=101)

        async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
            self.sent_messages.append((chat_id, text, reply_markup))
            return SimpleNamespace(message_id=102)

        async def send_media_group(self, chat_id, media):
            return [SimpleNamespace(message_id=201), SimpleNamespace(message_id=202)]

        async def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
            self.edited_markups.append((chat_id, message_id, reply_markup))

    mock_bot = _MockBot()
    pub = Publisher(bot=mock_bot, repo=repo)

    markup = SimpleNamespace(inline_keyboard=[])

    # 1. Single photo delivery
    job1 = PublishJob(
        chat_id=chat_id,
        text="single",
        gallery=[("photo.jpg", False)],
        reply_markup=markup,
    )
    msg_id1 = await pub._deliver(job1)
    assert msg_id1 == 101
    assert len(mock_bot.sent_photos) == 1
    assert mock_bot.sent_photos[0][2] is markup

    # 2. Text fallback delivery
    job2 = PublishJob(chat_id=chat_id, text="text", gallery=[], reply_markup=markup)
    msg_id2 = await pub._deliver(job2)
    assert msg_id2 == 102
    assert len(mock_bot.sent_messages) == 1
    assert mock_bot.sent_messages[0][2] is markup

    # 3. Digest delivery with markup -> single photo so button is kept
    job3 = PublishJob(
        chat_id=chat_id,
        text="digest",
        gallery=[("p1.jpg", False), ("p2.jpg", False)],
        reply_markup=markup,
    )
    msg_id3 = await pub._deliver(job3)
    assert msg_id3 == 101
    assert len(mock_bot.sent_photos) == 2
    assert mock_bot.sent_photos[1][1] == "p1.jpg"
    assert mock_bot.sent_photos[1][2] is markup

    # 4. Digest delivery without markup -> media group
    job4 = PublishJob(
        chat_id=chat_id,
        text="digest_no_markup",
        gallery=[("p1.jpg", False), ("p2.jpg", False)],
        reply_markup=None,
    )
    msg_id4 = await pub._deliver(job4)
    assert msg_id4 == 201


async def test_a_picture_telegram_cannot_fetch_is_uploaded(repo, monkeypatch) -> None:
    """Telegram fetches a URL itself and sometimes cannot reach a platform's CDN:
    the bot fetches it and uploads the bytes, and only without them sends text."""
    from types import SimpleNamespace

    from aiogram.types import BufferedInputFile

    from bot.poller import publisher as publisher_module
    from bot.poller.publisher import Publisher, PublishJob

    class _Bot:
        def __init__(self) -> None:
            self.photos: list[object] = []
            self.texts: list[str] = []

        async def send_photo(self, chat_id, photo, **kwargs):
            if isinstance(photo, str):
                raise RuntimeError("Bad Request: failed to get HTTP URL content")
            self.photos.append(photo)
            return SimpleNamespace(message_id=7)

        async def send_message(self, chat_id, text, **kwargs):
            self.texts.append(text)
            return SimpleNamespace(message_id=8)

    async def fetched(url: str) -> bytes:
        return b"\xff\xd8\xffjpeg"

    bot = _Bot()
    monkeypatch.setattr(publisher_module.images, "fetch", fetched)
    job = PublishJob(chat_id=-1, text="card", gallery=[("https://cdn/x.png", False)])
    assert await Publisher(bot=bot, repo=repo)._deliver(job) == 7
    assert isinstance(bot.photos[0], BufferedInputFile) and not bot.texts

    async def nothing(url: str) -> None:
        return None

    monkeypatch.setattr(publisher_module.images, "fetch", nothing)
    assert await Publisher(bot=bot, repo=repo)._deliver(job) == 8
    assert bot.texts == ["card"]
