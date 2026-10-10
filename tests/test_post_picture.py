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


def _look(style: str, size: str = "1024x1024", scale: int = 3) -> post_picture.Look:
    return post_picture.Look(style, size, scale)


def _picture(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGB")


def test_a_low_res_icon_is_enlarged_three_times_on_a_1024_square() -> None:
    data = post_picture.compose(_png((64, 64)), _look(post_picture.STYLE_COLOR))
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
        assert (
            post_picture.compose(_png(size), _look(post_picture.STYLE_COVER), _png((300, 400)))
            is None
        )


def test_the_cover_style_puts_the_cover_round_the_icon() -> None:
    cover = _png((300, 400), (20, 200, 20, 255))
    data = post_picture.compose(_png((64, 64)), _look(post_picture.STYLE_COVER), cover)
    assert data is not None
    corner = _picture(data).getpixel((3, 3))
    assert corner[1] > corner[0]  # green, from the cover — not the icon's red


def test_without_a_cover_the_cover_style_falls_back_to_the_colour() -> None:
    data = post_picture.compose(_png((64, 64)), _look(post_picture.STYLE_COVER), None)
    assert data is not None
    corner = _picture(data).getpixel((3, 3))
    assert corner[0] > corner[1]


def test_off_or_not_a_picture_draws_nothing() -> None:
    assert post_picture.compose(_png((64, 64)), _look(post_picture.STYLE_OFF)) is None
    assert post_picture.compose(b"not a picture", _look(post_picture.STYLE_COLOR)) is None


async def test_build_reads_the_first_source_that_loads(tmp_path, monkeypatch) -> None:
    small = tmp_path / "icon.png"
    small.write_bytes(_png((64, 64), (10, 20, 230, 255)))
    large = tmp_path / "art.png"
    large.write_bytes(_png((1024, 1024)))

    async def nothing(url: str) -> None:
        return None

    monkeypatch.setattr(post_picture.images, "fetch", nothing)
    missing = str(tmp_path / "gone.png")
    color = _look(post_picture.STYLE_COLOR)
    assert await post_picture.build((missing, str(small)), (), color) is not None
    assert await post_picture.build((str(large),), (), color) is None
    assert await post_picture.build((str(small),), (), _look(post_picture.STYLE_OFF)) is None
    cover = _look(post_picture.STYLE_COVER)
    assert await post_picture.build(("https://cdn/x.png",), (), cover) is None


async def test_the_admin_picks_the_style_the_card_and_the_scale(repo) -> None:
    from bot.services import admin_registry

    # On by default (owner, 2026-10-10): the icon's colour, 1024, x4.
    assert await post_picture.look_of(repo) == post_picture.Look("color", "1024x1024", 4)
    await admin_registry.set_value(repo, "global", post_picture.STYLE_KEY, "cover", None)
    await admin_registry.set_value(repo, "global", post_picture.SIZE_KEY, "720x1280", None)
    await admin_registry.set_value(repo, "global", post_picture.SCALE_KEY, "8", None)
    assert await post_picture.look_of(repo) == post_picture.Look("cover", "720x1280", 8)
    # The DM test's own style wins over the admin's; the card and scale stay.
    assert await post_picture.look_of(repo, "color") == post_picture.Look("color", "720x1280", 8)


def test_the_card_size_and_scale_are_the_admins() -> None:
    icon = _png((64, 64))
    tall = _picture(post_picture.compose(icon, _look("color", "720x1280", 2)))
    assert tall.size == (720, 1280)
    # x2 of 64 px in the middle of the card; outside it, the ground.
    # (The icon is red 200; the ground, its colour toned down, stays below.)
    assert tall.getpixel((360, 640))[0] > 190
    assert tall.getpixel((360 + 60, 640))[0] > 190
    assert tall.getpixel((360 + 80, 640 - 80))[0] < 190
    alone = _picture(post_picture.compose(icon, _look("color", "original", 5)))
    assert alone.size == (320, 320)
    once = _picture(post_picture.compose(icon, _look("cover", "original", 1)))
    assert once.size == (64, 64)


def test_an_icon_never_takes_more_than_90_percent_of_its_card() -> None:
    """Owner, 2026-10-10: a zoom past the card is held at 90% of it."""
    card = _picture(post_picture.compose(_png((190, 190)), _look("color", "720x1280", 4)))
    assert card.size == (720, 1280)
    # 190 x 4 = 760 > 720: held at 90% of 720, 648 px.
    assert card.getpixel((360 + 318, 640))[0] > 190
    assert card.getpixel((360 + 330, 640))[0] < 190
    # 64 x 8 = 512 fits: enlarged as asked.
    fits = _picture(post_picture.compose(_png((64, 64)), _look("color", "720x1280", 8)))
    assert fits.getpixel((360 + 250, 640))[0] > 190
    assert fits.getpixel((360 + 270, 640))[0] < 190


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
    await admin_registry.set_value(repo, "global", post_picture.STYLE_KEY, "off", None)
    assert await pub._deliver(job(small, "https://cdn/icon.png")) == 5
    assert sent == ["https://cdn/icon.png"]

    await admin_registry.set_value(repo, "global", post_picture.STYLE_KEY, "color", None)
    await pub._deliver(job(small, "https://cdn/icon.png"))
    assert isinstance(sent[-1], BufferedInputFile)
    assert _picture(sent[-1].data).size == (1024, 1024)

    await pub._deliver(job(large, "https://cdn/art.png"))
    assert sent[-1] == "https://cdn/art.png"


async def test_the_notification_test_is_one_global_action(repo, settings) -> None:
    """One test for the whole app, beside the picture settings — not one per
    person's card (owner, 2026-10-10)."""
    from bot.services.admin_actions import AdminContext, Done, Target, available, perform

    views = await available(AdminContext(repo, settings), "global", Target(), locale="ru")
    assert [(v.id, v.target, v.section) for v in views] == [("notification_test", "all", "rules")]
    person = await repo.ensure_user(1, "someone")
    card = await available(AdminContext(repo, settings), "user", Target(person=person), locale="ru")
    assert "notification_test" not in [v.id for v in card]

    calls: list[None] = []

    async def samples() -> int:
        calls.append(None)
        return 6

    ctx = AdminContext(repo, settings, send_picture_samples=samples)
    done = await perform(
        ctx, "global", Target.decode("global", "all"), "notification_test", 0, locale="ru"
    )
    assert isinstance(done, Done) and done.ok and "6" in (done.text or "") and len(calls) == 1

    async def none() -> int:
        return 0

    ctx = AdminContext(repo, settings, send_picture_samples=none)
    done = await perform(ctx, "global", Target(), "notification_test", 0, locale="ru")
    assert isinstance(done, Done) and not done.ok


async def test_the_test_takes_each_platforms_newest_achievement_whoever_earned_it(repo) -> None:
    from datetime import timedelta

    from bot.db.repo import AchievementRow
    from bot.util import utcnow

    now = utcnow()

    def row(achievement_id: str, days: int, icon: str | None) -> AchievementRow:
        return AchievementRow(
            title_id="10",
            achievement_id=achievement_id,
            name=achievement_id,
            description=None,
            icon_url=icon,
            unlocked_at=(now - timedelta(days=days)).isoformat(timespec="seconds"),
            gamerscore=0,
            rarity_percent=None,
            platform="steam",
        )

    for tg_id, steam_id, rows in (
        (10, "76561190000000010", [row("old", 5, "https://e/old.png")]),
        (11, "76561190000000011", [row("new", 1, "https://e/new.png"), row("bare", 0, None)]),
    ):
        await repo.ensure_user(tg_id, f"p{tg_id}")
        person = await repo.person_id(tg_id)
        await repo.link_platform_account(person, "steam", steam_id, f"P{tg_id}")
        await repo.insert_new_achievements_steam(person, steam_id, rows, is_backfill=False)

    latest = await repo.latest_per_platform()
    # The newest one with a picture — the one with none is passed over.
    assert [(r.platform, r.achievement_id) for r in latest] == [("steam", "new")]
    assert latest[0].person_id == await repo.person_id(11)


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


async def test_the_bots_rules_screen_carries_the_test_button(repo) -> None:
    from bot.services.admin_registry import values
    from bot.views.admin import global_actions
    from bot.views.admin_settings import render_settings_group

    actions = await global_actions(repo, locale="ru")
    current = await values(repo, "global")
    _text, markup = render_settings_group("rules", current, locale="ru", actions=actions).as_pair()
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "a:x:g:all:notification_test:0" in data
    _text, markup = render_settings_group("lists", current, locale="ru", actions=actions).as_pair()
    assert "a:x:g:all:notification_test:0" not in [
        b.callback_data for row in markup.inline_keyboard for b in row
    ]
