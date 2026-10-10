"""services/post_picture.py: a post's picture laid out on a square (owner,
2026-10-10), and the publisher sending it."""

from __future__ import annotations

import io

from PIL import Image

from bot.services import post_picture


def _png(size: tuple[int, int], color=(200, 30, 30, 255)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, "PNG")
    return out.getvalue()


def _size(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


def test_a_small_icon_lands_in_the_middle_of_a_square() -> None:
    data = post_picture.compose(_png((64, 64)), post_picture.STYLE_COLOR)
    assert data is not None and _size(data) == (post_picture.SIDE, post_picture.SIDE)
    picture = Image.open(io.BytesIO(data)).convert("RGB")
    middle = picture.getpixel((post_picture.SIDE // 2, post_picture.SIDE // 2))
    corner = picture.getpixel((2, 2))
    # The icon's own red in the middle, a darker ground of its colour round it.
    assert middle[0] > 150 and middle[1] < 80
    assert sum(corner) < sum(middle)


def test_the_cover_style_puts_the_cover_round_the_icon() -> None:
    cover = _png((300, 400), (20, 200, 20, 255))
    data = post_picture.compose(_png((64, 64)), post_picture.STYLE_COVER, cover)
    assert data is not None
    corner = Image.open(io.BytesIO(data)).convert("RGB").getpixel((5, 5))
    assert corner[1] > corner[0]  # green, from the cover — not the icon's red


def test_without_a_cover_the_cover_style_falls_back_to_the_colour() -> None:
    data = post_picture.compose(_png((64, 64)), post_picture.STYLE_COVER, None)
    assert data is not None
    corner = Image.open(io.BytesIO(data)).convert("RGB").getpixel((5, 5))
    assert corner[0] > corner[1]


def test_large_artwork_keeps_its_whole_picture_on_a_square() -> None:
    assert _size(post_picture.compose(_png((1920, 1080)), post_picture.STYLE_COLOR)) == (
        post_picture.SIDE,
        post_picture.SIDE,
    )
    assert _size(post_picture.compose(_png((800, 800)), post_picture.STYLE_COVER)) == (
        post_picture.SIDE,
        post_picture.SIDE,
    )


def test_something_that_is_not_a_picture_is_refused() -> None:
    assert post_picture.compose(b"not a picture", post_picture.STYLE_COLOR) is None


async def test_build_reads_the_first_source_that_loads(tmp_path, monkeypatch) -> None:
    icon = tmp_path / "icon.png"
    icon.write_bytes(_png((64, 64), (10, 20, 230, 255)))

    async def nothing(url: str) -> None:
        return None

    monkeypatch.setattr(post_picture.images, "fetch", nothing)
    missing = str(tmp_path / "gone.png")
    data = await post_picture.build((missing, str(icon)), (), post_picture.STYLE_COLOR)
    assert data is not None
    assert await post_picture.build((str(icon),), (), post_picture.STYLE_OFF) is None
    assert await post_picture.build(("https://cdn/x.png",), (), post_picture.STYLE_COVER) is None


async def test_the_style_is_off_until_the_admin_picks_one(repo) -> None:
    from bot.services import admin_registry

    assert await post_picture.style_of(repo) == post_picture.STYLE_OFF
    await admin_registry.set_value(repo, "global", post_picture.STYLE_KEY, "cover", None)
    assert await post_picture.style_of(repo) == post_picture.STYLE_COVER


async def test_the_publisher_sends_the_square_and_only_while_a_style_is_on(
    repo, monkeypatch, tmp_path
) -> None:
    from types import SimpleNamespace

    from aiogram.types import BufferedInputFile

    from bot.poller.publisher import Art, Publisher, PublishJob
    from bot.services import admin_registry

    icon = tmp_path / "icon.png"
    icon.write_bytes(_png((64, 64)))
    sent: list[object] = []

    class _Bot:
        async def send_photo(self, chat_id, photo, **kwargs):
            sent.append(photo)
            return SimpleNamespace(message_id=5)

    job = PublishJob(
        chat_id=-1,
        text="card",
        gallery=[("https://cdn/icon.png", False)],
        art=[Art((str(icon), "https://cdn/icon.png"))],
    )
    pub = Publisher(bot=_Bot(), repo=repo)
    assert await pub._deliver(job) == 5
    assert sent == ["https://cdn/icon.png"]

    await admin_registry.set_value(repo, "global", post_picture.STYLE_KEY, "color", None)
    assert await pub._deliver(job) == 5
    assert isinstance(sent[-1], BufferedInputFile)
    assert _size(sent[-1].data) == (post_picture.SIDE, post_picture.SIDE)


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
