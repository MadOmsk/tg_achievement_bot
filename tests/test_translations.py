"""The developers' posts put into Russian ahead of anybody reading them."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from bot.db.repo import Repo
from bot.db.repo._steam import StoredPatch
from bot.poller import translations
from bot.services import news_translations, steam_extras
from bot.services.game_descriptions import GameTranslator
from bot.services.guide_translations import GuideTranslator
from bot.web.mini_chat import news_text, news_title


class _Auth:
    async def get_key(self) -> str:
        return "key"


def _post(gid: str, text: str, day: str) -> StoredPatch:
    return StoredPatch(
        gid=gid, title=f"Update {gid}", published_at=day, text_en=text,
        title_ru=None, text_ru=None,
    )  # fmt: skip


@pytest.mark.asyncio
async def test_the_newest_posts_are_translated_and_a_changed_one_again(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    async def translate(api_key: str, title: str, text: str) -> tuple[str, str]:
        asked.append(title)
        return f"RU {title}", f"RU {text}"

    monkeypatch.setattr(news_translations, "translate_news", translate)
    await repo.save_game_patches(
        10,
        [
            _post("1", "Old fixes.", "2026-01-01T00:00:00Z"),
            _post("2", "New fixes.", "2026-10-29T00:00:00Z"),
            _post("3", "x" * (news_translations.MAX_CHARS + 1), "2026-10-30T00:00:00Z"),
        ],
    )
    await repo.set_app_setting(translations.QUEUE_KEY, "1")
    walker = translations.Translations(
        repo,
        news_translations.NewsTranslator(repo, _Auth()),
        GuideTranslator(repo, _Auth()),
        GameTranslator(repo, _Auth()),
    )
    await walker.tick()
    assert asked == ["Update 2", "Update 1"]  # the newest first; too long stays English

    post = await repo.game_patch(10, "2")
    assert (news_title(post, "ru"), news_text(post, "ru")) == ("RU Update 2", "RU New fixes.")
    assert (news_title(post, "en"), news_text(post, "en")) == ("Update 2", "New fixes.")

    # Read again unchanged: the translation stays; changed: it goes, to be made again.
    await repo.save_game_patches(10, [_post("2", "New fixes.", "2026-10-29T00:00:00Z")])
    assert (await repo.game_patch(10, "2")).title_ru == "RU Update 2"
    await repo.save_game_patches(10, [_post("2", "Newer fixes.", "2026-10-29T00:00:00Z")])
    post = await repo.game_patch(10, "2")
    assert post.title_ru is None
    assert news_text(post, "ru") == "Newer fixes."
    walker._next_batch = 0
    await walker.tick()
    assert (await repo.game_patch(10, "2")).text_ru == "RU Newer fixes."


@pytest.mark.asyncio
async def test_a_failed_post_rests(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[str] = []

    async def fail(api_key: str, title: str, text: str) -> None:
        asked.append(title)

    monkeypatch.setattr(news_translations, "translate_news", fail)
    await repo.save_game_patches(10, [_post("1", "Fixes.", "2026-10-29T00:00:00Z")])
    await repo.set_app_setting(translations.QUEUE_KEY, "1")
    walker = translations.Translations(
        repo,
        news_translations.NewsTranslator(repo, _Auth()),
        GuideTranslator(repo, _Auth()),
        GameTranslator(repo, _Auth()),
    )
    await walker.tick()
    walker._next_batch = 0
    await walker.tick()
    assert asked == ["Update 1"]


@pytest.mark.asyncio
async def test_a_post_is_translated_when_read(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    async def translate(api_key: str, title: str, text: str) -> tuple[str, str]:
        return f"RU {title}", f"RU {text}"

    async def fetch(appid: int) -> list:
        return [
            SimpleNamespace(
                gid="9", title="Update 9", date="2026-10-30T00:00:00Z", text="Fixes.",
                kind="patch", image=None,
            )
        ]  # fmt: skip

    monkeypatch.setattr(news_translations, "translate_news", translate)
    monkeypatch.setattr(steam_extras, "fetch_patches", fetch)
    news = news_translations.NewsTranslator(repo, _Auth())
    extras = steam_extras.SteamExtras(repo, None, None)
    extras.on_posts_saved = news.later
    await repo.save_game_patches(20, [_post("1", "Old.", "2026-01-01T00:00:00Z")])
    await extras.refresh_patches(20)
    await asyncio.gather(*news._tasks)
    assert (await repo.game_patch(20, "9")).title_ru == "RU Update 9"
    assert (await repo.game_patch(20, "1")).title_ru == "RU Update 1"


def test_a_long_post_is_cut_between_paragraphs(monkeypatch: pytest.MonkeyPatch) -> None:
    from bot.services.translate import client

    monkeypatch.setattr(client, "NEWS_PART_CHARS", 50)
    text = "Para one line a.\nPara one line b.\n\nPara two is here.\nmore two.\n\nThird."
    assert client._news_parts(text) == [
        "Para one line a.\nPara one line b.",
        "Para two is here.\nmore two.\n\nThird.",
    ]
    assert client._news_parts("short") == ["short"]


@pytest.mark.asyncio
async def test_tips_go_into_the_other_language_and_a_changed_one_again(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bot.services import guide_translations

    asked: list[tuple[str, list[str]]] = []

    async def translate(api_key: str, tips: list, *, target_language: str) -> list[str]:
        asked.append((target_language, [tip for _, _, tip in tips]))
        return [f"{target_language}: {tip}" for _, _, tip in tips]

    monkeypatch.setattr(guide_translations, "translate_guides", translate)
    for achievement_id in ("a", "b"):
        await repo._conn.execute(
            "INSERT INTO title_achievements (platform, title_id, achievement_id, name_en,"
            " updated_at) VALUES ('steam', '7', ?, ?, '2026-10-30')",
            (achievement_id, f"Name {achievement_id}"),
        )
    await repo._conn.commit()
    await repo.replace_title_tips(
        "steam", "7", {"a": ("Go left.", "g1"), "b": ("Иди направо.", "g2")}, complete=True
    )
    tips = guide_translations.GuideTranslator(repo, _Auth())
    await tips.translate_some(1)
    assert sorted(asked) == [("en", ["Иди направо."]), ("ru", ["Go left."])]
    assert await repo.title_tips("steam", "7") == {
        "a": ("Go left.", "ru: Go left."),
        "b": ("en: Иди направо.", "Иди направо."),
    }

    await repo.replace_title_tips("steam", "7", {"a": ("Go right.", "g1")}, complete=False)
    assert (await repo.title_tips("steam", "7"))["a"] == ("Go right.", None)
    await repo.replace_title_tips("steam", "7", {"b": ("Иди направо.", "g2")}, complete=False)
    assert (await repo.title_tips("steam", "7"))["b"] == ("en: Иди направо.", "Иди направо.")
    await tips.translate_some(1)
    assert (await repo.title_tips("steam", "7"))["a"] == ("Go right.", "ru: Go right.")


@pytest.mark.asyncio
async def test_a_new_post_is_told_about_once_translated(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def translate(api_key: str, title: str, text: str) -> tuple[str, str]:
        return f"RU {title}", f"RU {text}"

    async def fetch(appid: int) -> list:
        return [
            SimpleNamespace(
                gid="9", title="Update 9", date="2026-10-30T00:00:00Z", text="Fixes.",
                kind="patch", image=None,
            )
        ]  # fmt: skip

    told: list[str | None] = []

    async def tell(appid: int, posts: list) -> None:
        told.extend(post.title_ru for post in posts)

    monkeypatch.setattr(news_translations, "translate_news", translate)
    monkeypatch.setattr(steam_extras, "fetch_patches", fetch)
    news = news_translations.NewsTranslator(repo, _Auth())
    extras = steam_extras.SteamExtras(repo, None, None)
    extras.translate_posts = news.translate_app
    extras.on_posts_saved = news.later
    extras.on_new_posts = tell
    await repo.save_game_patches(30, [_post("1", "Old.", "2026-01-01T00:00:00Z")])
    await extras.refresh_patches(30)
    assert told == ["RU Update 9"]
