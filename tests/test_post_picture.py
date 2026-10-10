"""services/post_picture.py: a low-resolution post picture enlarged on a
square, a high-resolution one left as it is (owner, 2026-10-10)."""

from __future__ import annotations

import io

from PIL import Image

from bot.services import post_picture


def _png(size: tuple[int, int], color=(200, 30, 30, 255)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, "PNG")
    return out.getvalue()


def _picture(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def test_a_low_res_icon_is_enlarged_three_times_on_a_1024_square() -> None:
    data = post_picture.compose(_png((64, 64)), post_picture.STYLE_COLOR)
    assert data is not None
    picture = _picture(data)
    assert picture.size == (1024, 1024)
    # The icon's own red, 192 px across in the middle; a darker ground of its
    # colour round it.
    middle = picture.getpixel((512, 512))
    assert middle[0] > 150 and middle[1] < 80
    assert picture.getpixel((512 + 90, 512))[0] > 150
    outside = picture.getpixel((512 + 110, 512 - 110))
    assert sum(outside) < sum(middle)
    assert sum(picture.getpixel((1, 1))) < sum(middle)


def test_a_high_res_picture_is_left_as_it_is() -> None:
    for size in ((256, 256), (1920, 1080), (240, 240)):
        assert post_picture.compose(_png(size), post_picture.STYLE_COVER, _png((300, 400))) is None


def test_the_cover_style_puts_the_cover_round_the_icon() -> None:
    cover = _png((300, 400), (20, 200, 20, 255))
    data = post_picture.compose(_png((64, 64)), post_picture.STYLE_COVER, cover)
    assert data is not None
    corner = _picture(data).getpixel((3, 3))
    assert corner[1] > corner[0]  # green, from the cover — not the icon's red


def test_without_a_cover_the_cover_style_falls_back_to_the_colour() -> None:
    data = post_picture.compose(_png((64, 64)), post_picture.STYLE_COVER, None)
    assert data is not None
    corner = _picture(data).getpixel((3, 3))
    assert corner[0] > corner[1]


def test_off_or_not_a_picture_draws_nothing() -> None:
    assert post_picture.compose(_png((64, 64)), post_picture.STYLE_OFF) is None
    assert post_picture.compose(b"not a picture", post_picture.STYLE_COLOR) is None


async def test_build_reads_the_first_source_that_loads(tmp_path, monkeypatch) -> None:
    small = tmp_path / "icon.png"
    small.write_bytes(_png((64, 64), (10, 20, 230, 255)))
    large = tmp_path / "art.png"
    large.write_bytes(_png((1024, 1024)))

    async def nothing(url: str) -> None:
        return None

    monkeypatch.setattr(post_picture.images, "fetch", nothing)
    missing = str(tmp_path / "gone.png")
    color = post_picture.STYLE_COLOR
    assert await post_picture.build((missing, str(small)), (), color) is not None
    assert await post_picture.build((str(large),), (), color) is None
    assert await post_picture.build((str(small),), (), post_picture.STYLE_OFF) is None
    assert await post_picture.build(("https://cdn/x.png",), (), post_picture.STYLE_COVER) is None


async def test_the_style_is_off_until_the_admin_picks_one(repo) -> None:
    from bot.services import admin_registry

    assert await post_picture.style_of(repo) == post_picture.STYLE_OFF
    await admin_registry.set_value(repo, "global", post_picture.STYLE_KEY, "cover", None)
    assert await post_picture.style_of(repo) == post_picture.STYLE_COVER


async def test_the_publisher_enlarges_only_a_low_res_icon_and_only_while_on(
    repo, monkeypatch, tmp_path
) -> None:
    from types import SimpleNamespace

    from aiogram.types import BufferedInputFile

    from bot.poller.publisher import Art, Publisher, PublishJob
    from bot.services import admin_registry

    small = tmp_path / "icon.png"
    small.write_bytes(_png((64, 64)))
    large = tmp_path / "art.png"
    large.write_bytes(_png((1280, 720)))
    sent: list[object] = []

    class _Bot:
        async def send_photo(self, chat_id, photo, **kwargs):
            sent.append(photo)
            return SimpleNamespace(message_id=5)

    def job(path, url):
        return PublishJob(
            chat_id=-1, text="card", gallery=[(url, False)], art=[Art((str(path), url))]
        )

    pub = Publisher(bot=_Bot(), repo=repo)
    assert await pub._deliver(job(small, "https://cdn/icon.png")) == 5
    assert sent == ["https://cdn/icon.png"]

    await admin_registry.set_value(repo, "global", post_picture.STYLE_KEY, "color", None)
    await pub._deliver(job(small, "https://cdn/icon.png"))
    assert isinstance(sent[-1], BufferedInputFile)
    assert _picture(sent[-1].data).size == (1024, 1024)

    await pub._deliver(job(large, "https://cdn/art.png"))
    assert sent[-1] == "https://cdn/art.png"


async def test_the_test_action_hands_the_person_to_the_panels_sender(repo, settings) -> None:
    from bot.services.admin_actions import AdminContext, Done, Target, perform

    person = await repo.ensure_user(1, "someone")
    asked: list[int] = []

    async def samples(person_id: int) -> int:
        asked.append(person_id)
        return 6

    ctx = AdminContext(repo, settings, send_picture_samples=samples)
    done = await perform(ctx, "user", Target(person=person), "picture_test", 0, locale="ru")
    assert isinstance(done, Done) and done.ok and "6" in (done.text or "")
    assert asked == [person]

    async def none(person_id: int) -> int:
        return 0

    ctx = AdminContext(repo, settings, send_picture_samples=none)
    done = await perform(ctx, "user", Target(person=person), "picture_test", 0, locale="ru")
    assert isinstance(done, Done) and not done.ok


async def test_the_sample_is_the_whole_post_in_the_style_asked(repo, tmp_path, monkeypatch) -> None:
    """The super-admin's test sends what a chat would get — text, picture —
    in the style asked, whatever the admin's setting, and records nothing."""
    from types import SimpleNamespace

    from aiogram.types import BufferedInputFile

    from bot.db.repo import AchievementRow
    from bot.poller.publisher import Publisher
    from bot.services import achievement_icons

    icon = tmp_path / "icon.png"
    icon.write_bytes(_png((64, 64)))
    monkeypatch.setattr(achievement_icons, "find_cached_icon", lambda *a, **k: icon)
    sent: list[tuple[object, dict]] = []

    class _Bot:
        async def send_photo(self, chat_id, photo, **kwargs):
            sent.append((photo, kwargs))
            return SimpleNamespace(message_id=11)

    person = await repo.ensure_user(1, "someone")
    item = AchievementRow(
        title_id="t1",
        achievement_id="a1",
        name="Оружейный мастер",
        description="Улучшите оружие.",
        icon_url="https://cdn/icon.png",
        unlocked_at=None,
        gamerscore=0,
        rarity_percent=80.4,
        platform="steam",
        title_name="Resident Evil 3",
    )
    pub = Publisher(bot=_Bot(), repo=repo)
    assert await pub.sample(item, person, 42, locale="ru", style="cover", note="обложка") == 11
    photo, kwargs = sent[-1]
    assert isinstance(photo, BufferedInputFile)
    assert "Оружейный мастер" in kwargs["caption"] and "<i>обложка</i>" in kwargs["caption"]
    assert await pub.sample(item, person, 42, locale="ru", style="off", note="как есть") == 11
    assert sent[-1][0] == "https://cdn/icon.png"
