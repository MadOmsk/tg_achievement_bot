"""A picture chosen in the Mini App (#157, migration 077): decoded and saved
again, removed with the account, and taken down by a super-admin."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from bot.db.repo import Repo
from bot.services import avatars, custom_avatars
from bot.web.mini_api import cors_middleware, setup_mini_api
from tests.test_mini_delete import _signed_init_data


def _photo(size: tuple[int, int] = (1600, 1200), *, fmt: str = "JPEG", gps: bool = False) -> bytes:
    image = Image.new("RGB", size, (200, 30, 30))
    out = io.BytesIO()
    if gps:
        exif = Image.Exif()
        exif[0x8825] = {2: (55.0, 45.0, 0.0), 4: (37.0, 37.0, 0.0)}  # GPSInfo
        image.save(out, format=fmt, exif=exif)
    else:
        image.save(out, format=fmt)
    return out.getvalue()


def test_a_picture_is_saved_again_as_a_small_jpeg_without_exif() -> None:
    picture = custom_avatars.normalize(_photo(gps=True))
    assert picture is not None
    with Image.open(io.BytesIO(picture)) as image:
        assert image.format == "JPEG"
        assert max(image.size) == custom_avatars.SIDE
        assert not image.getexif()


def test_png_and_webp_are_accepted_too() -> None:
    assert custom_avatars.normalize(_photo((64, 64), fmt="PNG")) is not None
    assert custom_avatars.normalize(_photo((64, 64), fmt="WEBP")) is not None


def test_anything_that_is_not_an_image_is_refused() -> None:
    assert custom_avatars.normalize(b"\xff\xd8\xff<html>not a jpeg</html>") is None
    assert custom_avatars.normalize(b"") is None
    gif = io.BytesIO()
    Image.new("RGB", (8, 8)).save(gif, format="GIF")
    assert custom_avatars.normalize(gif.getvalue()) is None


def test_a_huge_canvas_is_refused_before_decoding(monkeypatch) -> None:
    monkeypatch.setattr(custom_avatars, "MAX_PIXELS", 100)
    assert custom_avatars.normalize(_photo((20, 20))) is None


async def test_a_new_picture_replaces_the_file_and_clear_removes_it(
    repo: Repo, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    await repo.ensure_user(1, "someone")
    assert await custom_avatars.store(repo, await repo.person_id(1), _photo())
    first = await repo.custom_avatar_path(await repo.person_id(1))
    assert first and (avatars.avatar_dir() / first).is_file()

    assert await custom_avatars.store(repo, await repo.person_id(1), _photo((300, 300)))
    second = await repo.custom_avatar_path(await repo.person_id(1))
    assert second != first
    assert not (avatars.avatar_dir() / first).exists()

    assert not await custom_avatars.store(repo, await repo.person_id(1), b"nonsense")
    assert await repo.custom_avatar_path(await repo.person_id(1)) == second

    assert await custom_avatars.clear(repo, await repo.person_id(1))
    assert await repo.custom_avatar_path(await repo.person_id(1)) is None
    assert not (avatars.avatar_dir() / second).exists()
    assert not await custom_avatars.clear(repo, await repo.person_id(1))


async def test_deleting_the_account_removes_the_chosen_picture(
    repo: Repo, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    await repo.ensure_user(1, "someone")
    await custom_avatars.store(repo, await repo.person_id(1), _photo())
    path = avatars.avatar_dir() / (await repo.custom_avatar_path(await repo.person_id(1)))
    assert path.is_file()
    await repo.delete_user(1)
    assert not path.exists()


async def test_the_endpoint_says_invalid_for_a_body_too_big_or_not_an_image(
    repo: Repo, settings, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    headers = {"X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), 42)}
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        # Over aiohttp's own 1 MB, under ours: still read, shrunk and stored.
        noisy = Image.effect_noise((900, 900), 120).convert("RGB")
        out = io.BytesIO()
        noisy.save(out, format="PNG")
        big = out.getvalue()
        assert 1024 * 1024 < len(big) < custom_avatars.MAX_UPLOAD_BYTES
        ok = await client.put("/api/mini/me/avatar", data=big, headers=headers)
        assert ok.status == 200 and (await ok.json())["avatar_custom"] is True

        too_big = b"\x89PNG" + b"0" * custom_avatars.MAX_UPLOAD_BYTES
        resp = await client.put("/api/mini/me/avatar", data=too_big, headers=headers)
        assert (resp.status, (await resp.json())["error"]) == (400, "invalid")

        resp = await client.put("/api/mini/me/avatar", data=b"RIFF....WEBPjunk", headers=headers)
        assert (resp.status, (await resp.json())["error"]) == (400, "invalid")
    finally:
        await client.close()


async def test_the_super_admin_can_take_a_picture_down(
    repo: Repo, tmp_path: Path, monkeypatch
) -> None:
    from bot.handlers import admin as admin_handlers
    from bot.views.admin import render_user_card

    monkeypatch.chdir(tmp_path)
    await repo.ensure_user(7, "player7")
    await repo.link_xbox_account(await repo.person_id(7), "x7", "Tag7", 100)
    _text, markup = await render_user_card(repo, 7, locale="ru")
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "a:avclr:7" not in data

    await custom_avatars.store(repo, await repo.person_id(7), _photo())
    _text, markup = await render_user_card(repo, 7, locale="ru")
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "a:avclr:7" in data

    answered: list[str] = []
    redrawn: list[object] = []

    async def answer(text: str | None = None, **_kw) -> None:
        answered.append(text or "")

    async def fake_redraw(_callback, *args, **_kw) -> None:
        redrawn.append(args)

    monkeypatch.setattr(admin_handlers, "_redraw", fake_redraw)
    callback = SimpleNamespace(data="a:avclr:7", answer=answer)
    await admin_handlers.user_avatar_reset(callback, repo, SimpleNamespace(locale="ru"))
    assert await repo.custom_avatar_path(await repo.person_id(7)) is None
    assert answered and redrawn
