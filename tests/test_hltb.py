"""HowLongToBeat: search/cache service, chat-recent shortcuts, and the
handler's pure formatting/pagination logic (SPEC 6.6). No network — the
howlongtobeatpy calls themselves are out of scope for a unit test."""

from __future__ import annotations

from datetime import timedelta

from bot.db.repo import Repo, TitleHistoryRow
from bot.services.hltb import (
    HltbResult,
    _clean,
    _clean_query,
    _pick_fallback_word,
    details_of_entry,
    result_from_entry,
)
from bot.views.hltb import (
    DESCRIPTION_LIMIT,
    _card,
    _label,
    _recent_keyboard,
    _results_keyboard,
    _shorten,
)

CHAT_ID = -100777


def result(hltb_id: int = 1, year: int | None = 2021) -> HltbResult:
    return HltbResult(
        hltb_id=hltb_id,
        name="Halo Infinite",
        release_year=year,
        main_hours=11.3,
        extra_hours=19.5,
        completionist_hours=29.2,
        platforms=["PC", "Xbox Series X/S"],
        game_url="https://howlongtobeat.com/game/1",
        image_url="https://howlongtobeat.com/games/1_Halo_Infinite.jpg",
        genre="First-Person, Shooter",
        description_en="The Master Chief returns.",
        description_ru="Мастер Чиф возвращается.",
    )


def test_clean_treats_zero_and_none_as_no_data() -> None:
    assert _clean(None) is None
    assert _clean(0) is None
    assert _clean(0.0) is None
    assert _clean(11.3) == 11.3


def test_clean_query_strips_trademark_symbols() -> None:
    # Real Xbox title names, not made up (SPEC 6.6) — HLTB's own search
    # chokes on this clutter that Xbox's titlehub happily includes.
    assert _clean_query("HELLDIVERS™ 2") == "HELLDIVERS 2"
    assert _clean_query("Minecraft Legends© - Windows") == "Minecraft Legends - Windows"
    assert _clean_query("Some Game®") == "Some Game"


def test_clean_query_strips_separator_punctuation_without_gluing_words() -> None:
    assert _clean_query("Halo: Reach") == "Halo Reach"
    assert _clean_query("Assassin's Creed, Valhalla") == "Assassin's Creed Valhalla"


def test_clean_query_collapses_the_extra_whitespace_it_creates() -> None:
    assert _clean_query("Game™:  Subtitle") == "Game Subtitle"


def test_clean_query_leaves_an_ordinary_title_untouched() -> None:
    assert _clean_query("Gears of War 3") == "Gears of War 3"


def test_pick_fallback_word_takes_the_first_real_word() -> None:
    # The actual motivating case (SPEC 6.6): HLTB finds nothing for the full
    # string but does for "Dishonored" alone.
    assert _pick_fallback_word("Dishonored Definitive Edition PC") == "Dishonored"


def test_pick_fallback_word_skips_a_leading_stopword() -> None:
    assert _pick_fallback_word("The Last of Us") == "Last"


def test_pick_fallback_word_skips_multiple_leading_stopwords_in_a_row() -> None:
    # Not just one skip — every word is checked in turn until a real one
    # turns up, however many exceptions come first.
    assert _pick_fallback_word("PC The Witcher 3") == "Witcher"


def test_pick_fallback_word_is_none_for_a_single_word_query() -> None:
    # Retrying with the exact same string that already found nothing would
    # just repeat the failed search.
    assert _pick_fallback_word("Control") is None


def test_pick_fallback_word_is_none_when_every_word_is_a_stopword() -> None:
    assert _pick_fallback_word("of the it") is None


def test_label_includes_year_when_known() -> None:
    assert _label(result(year=2021)) == "Halo Infinite (2021)"
    assert _label(result(year=None)) == "Halo Infinite"


def test_card_shows_a_dash_for_missing_completion_times(i18n) -> None:
    incomplete = HltbResult(
        hltb_id=1,
        name="Coop Only",
        release_year=None,
        main_hours=None,
        extra_hours=None,
        completionist_hours=None,
        platforms=[],
        game_url=None,
        image_url=None,
        genre=None,
    )
    text = _card(incomplete, i18n)
    assert "Coop Only" in text
    assert "—" in text
    assert "None" not in text
    assert "Платформы" not in text  # nothing to show — no empty line either
    assert "howlongtobeat.com" not in text  # no link without a URL either


def test_card_lists_platforms_when_known(i18n) -> None:
    text = _card(result(), i18n)
    assert "Платформы: PC, Xbox Series X/S" in text


def test_card_links_to_the_hltb_page_when_known(i18n) -> None:
    text = _card(result(), i18n)
    assert '<a href="https://howlongtobeat.com/game/1">' in text


def test_card_shows_genre_when_known(i18n) -> None:
    text = _card(result(), i18n)
    assert "Жанры: First-Person, Shooter" in text


def test_card_separates_genre_from_platforms_with_a_blank_line(i18n) -> None:
    text = _card(result(), i18n)
    assert "Платформы: PC, Xbox Series X/S\n\nЖанры: First-Person, Shooter" in text


def test_card_shows_the_description_as_a_collapsed_blockquote(i18n) -> None:
    text = _card(result(), i18n)
    assert "<blockquote expandable>Мастер Чиф возвращается.</blockquote>" in text


def test_card_puts_the_description_before_the_link(i18n) -> None:
    # Agreed layout (#2, user request, 2026-09-12): the summary sits between
    # the genres and the HLTB link, not after it — the link is the card's
    # own last line, the way it was before descriptions existed.
    text = _card(result(), i18n)
    assert text.index("Мастер Чиф") < text.index("howlongtobeat.com/game/1")


def test_card_falls_back_to_english_when_there_is_no_translation(i18n) -> None:
    """An untranslated description still says more than none at all — the
    Russian side is filled in lazily, and this is what a card looks like in
    between (no Anthropic key, or the call having failed once)."""
    untranslated = result()
    untranslated.description_ru = None
    assert "The Master Chief returns." in _card(untranslated, i18n)


def test_card_has_no_description_block_when_hltb_has_no_summary(i18n) -> None:
    without = result()
    without.description_en = without.description_ru = None
    assert "blockquote" not in _card(without, i18n)


def test_card_escapes_html_in_the_description(i18n) -> None:
    tricky = result()
    tricky.description_ru = "Half-Life <b>2</b> & friends"
    text = _card(tricky, i18n)
    assert "<b>2</b>" not in text
    assert "Half-Life &lt;b&gt;2&lt;/b&gt; &amp; friends" in text


def test_description_follows_the_locale() -> None:
    r = result()
    assert r.description("ru") == "Мастер Чиф возвращается."
    assert r.description("en") == "The Master Chief returns."


def test_description_falls_back_to_whichever_side_exists() -> None:
    only_english = result()
    only_english.description_ru = None
    assert only_english.description("ru") == "The Master Chief returns."

    only_russian = result()
    only_russian.description_en = None
    assert only_russian.description("en") == "Мастер Чиф возвращается."


def test_shorten_cuts_a_long_description_on_a_word_boundary() -> None:
    # Telegram caps a photo caption at 1024 characters, and the card is a
    # caption whenever HLTB has cover art — an overlong summary would cost
    # the whole card, not just its own tail.
    long_text = "word " * 400
    shortened = _shorten(long_text)
    assert len(shortened) <= DESCRIPTION_LIMIT + 1  # the ellipsis itself
    assert shortened.endswith("…")
    assert "wor…" not in shortened  # never mid-word


def test_shorten_leaves_an_ordinary_description_untouched() -> None:
    assert _shorten("Short enough.") == "Short enough."


def test_card_uses_a_dot_separator_not_padding_spaces(i18n) -> None:
    text = _card(result(), i18n)
    assert "Основной сюжет · 11.3 ч" in text
    assert "     " not in text  # the old manual-alignment padding is gone


def test_card_escapes_html_in_external_hltb_text(i18n) -> None:
    tricky = HltbResult(
        hltb_id=1,
        name="<b>Evil</b> & Co",
        release_year=None,
        main_hours=None,
        extra_hours=None,
        completionist_hours=None,
        platforms=["A & B"],
        game_url=None,
        image_url=None,
        genre="Action & <Weird>",
    )
    text = _card(tricky, i18n)
    assert "<b>Evil</b> & Co" not in text
    assert "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in text
    assert "A &amp; B" in text
    assert "Action &amp; &lt;Weird&gt;" in text


def test_results_keyboard_paginates_five_per_page_with_nav(i18n) -> None:
    results = [result(hltb_id=i) for i in range(1, 13)]  # 12 -> 3 pages

    page0 = _results_keyboard(results, 0, 5, i18n)
    assert len(page0.inline_keyboard) == 7  # 5 picks + one nav row + cancel
    assert page0.inline_keyboard[-1][0].callback_data == "hltb:cancel"
    nav0 = page0.inline_keyboard[-2]
    assert [b.callback_data for b in nav0] == ["hltb:noop", "hltb:page:1"]  # no "back" on page 0
    assert nav0[0].text == "1/3"  # the page counter's label, not its (inert) callback_data

    page1 = _results_keyboard(results, 1, 5, i18n)
    nav1 = page1.inline_keyboard[-2]
    assert [b.callback_data for b in nav1] == ["hltb:page:0", "hltb:noop", "hltb:page:2"]
    assert nav1[1].text == "2/3"

    page2 = _results_keyboard(results, 2, 5, i18n)
    assert len(page2.inline_keyboard) == 4  # 2 leftover picks + nav + cancel
    nav2 = page2.inline_keyboard[-2]
    # no "forward" button on the last page
    assert [b.callback_data for b in nav2] == ["hltb:page:1", "hltb:noop"]


def test_results_keyboard_has_no_nav_row_for_a_single_page(i18n) -> None:
    results = [result(hltb_id=i) for i in range(1, 4)]
    markup = _results_keyboard(results, 0, 5, i18n)
    assert len(markup.inline_keyboard) == 4  # 3 picks + cancel, no nav
    picks, cancel = markup.inline_keyboard[:3], markup.inline_keyboard[3]
    assert all(row[0].callback_data.startswith("hltb:pick:") for row in picks)
    assert cancel[0].callback_data == "hltb:cancel"


def test_every_keyboard_offers_a_cancel_button(i18n) -> None:
    assert (
        _results_keyboard([result()], 0, 5, i18n).inline_keyboard[-1][0].callback_data
        == "hltb:cancel"
    )
    assert _recent_keyboard(["A"], 0, 5, i18n).inline_keyboard[-1][0].callback_data == "hltb:cancel"
    assert _recent_keyboard([], 0, 5, i18n).inline_keyboard[-1][0].callback_data == "hltb:cancel"


def test_results_keyboard_respects_a_custom_page_size(i18n) -> None:
    """The admin-configurable hltb_page_size (SPEC 6.4, 6.6) changes how many
    results/hints show per page, for both keyboards."""
    results = [result(hltb_id=i) for i in range(1, 5)]  # 4 results, page_size=2 -> 2 pages
    page0 = _results_keyboard(results, 0, 2, i18n)
    assert len(page0.inline_keyboard) == 4  # 2 picks + nav + cancel
    nav0 = page0.inline_keyboard[-2]
    assert nav0[0].text == "1/2"


def test_recent_keyboard_paginates_with_absolute_indices(i18n) -> None:
    """Button indices must stay absolute across pages — hltb_recent_pick
    looks games up by index into the *full* list, not the current page."""
    names = [f"Game {i}" for i in range(12)]  # 3 pages of 5

    page0 = _recent_keyboard(names, 0, 5, i18n)
    assert [row[0].callback_data for row in page0.inline_keyboard[:5]] == [
        f"hltb:qr:{i}" for i in range(5)
    ]
    nav0 = page0.inline_keyboard[-2]
    assert [b.callback_data for b in nav0] == ["hltb:noop", "hltb:rpage:1"]

    page2 = _recent_keyboard(names, 2, 5, i18n)
    assert [row[0].callback_data for row in page2.inline_keyboard[:2]] == [
        "hltb:qr:10",
        "hltb:qr:11",
    ]
    nav2 = page2.inline_keyboard[-2]
    assert [b.callback_data for b in nav2] == ["hltb:rpage:1", "hltb:noop"]


def test_recent_keyboard_has_no_nav_row_for_a_single_page(i18n) -> None:
    markup = _recent_keyboard(["A", "B"], 0, 5, i18n)
    assert len(markup.inline_keyboard) == 3  # 2 games + cancel, no nav


async def test_hltb_limits_are_admin_configurable(repo: Repo) -> None:
    assert await repo.get_int_setting("hltb_results_limit", 20) == 20  # default
    await repo.set_app_setting("hltb_results_limit", "7")
    assert await repo.get_int_setting("hltb_results_limit", 20) == 7

    assert await repo.get_int_setting("hltb_page_size", 5) == 5  # default
    await repo.set_app_setting("hltb_page_size", "3")
    assert await repo.get_int_setting("hltb_page_size", 5) == 3


async def test_chat_recent_games_orders_by_recency_and_dedupes(repo: Repo) -> None:
    """Same membership as /online and /who: subscribers union chat_seen, not
    only publishers (SPEC 6.6)."""
    await repo.upsert_chat(CHAT_ID, "Игровой чат", 1)

    await repo.ensure_user(1, "publisher")
    await repo.link_xbox_account(await repo.person_id(1), "xuid-a", "Publisher", 0)
    await repo.subscribe(CHAT_ID, await repo.person_id(1))

    await repo.ensure_user(2, "lurker")
    await repo.link_xbox_account(await repo.person_id(2), "xuid-b", "Lurker", 0)
    await repo.record_chat_seen(CHAT_ID, 2)  # in the chat, never subscribed

    await repo.ensure_user(3, "stranger")
    await repo.link_xbox_account(await repo.person_id(3), "xuid-c", "Stranger", 0)
    # tg_id 3 is connected but never seen or subscribed in this chat — must
    # not contribute games to it.

    def history(xuid: str, title_id: str, name: str, played_at: str) -> TitleHistoryRow:
        return TitleHistoryRow(
            title_id=title_id,
            name=name,
            platform="xbox_modern",
            current_gamerscore=0,
            max_gamerscore=0,
            achievements_unlocked=0,
            achievements_total=0,
            last_played_at=played_at,
        )

    await repo.save_title_history(
        "xuid-a",
        [history("xuid-a", "1", "Older Game", "2026-08-01T00:00:00+00:00")],
    )
    await repo.save_title_history(
        "xuid-b",
        [history("xuid-b", "2", "Newer Game", "2026-09-01T00:00:00+00:00")],
    )
    await repo.save_title_history(
        "xuid-c",
        [history("xuid-c", "3", "Stranger's Game", "2026-09-02T00:00:00+00:00")],
    )

    names = await repo.chat_recent_games(CHAT_ID)

    assert names == ["Newer Game", "Older Game"]


def _page(hltb_id: int, **fields: object) -> dict:
    game = {"game_id": hltb_id, "game_name": "Gears of War: E-Day", "game_type": "game"}
    game.update(fields)
    return {"game": [game]}


async def _store(repo: Repo, *, comp_main: int, year: int, days_ago: int, **extra: object) -> None:
    """An entry whose page was read `days_ago` days ago."""
    from bot.services.stores import hltb_page
    from bot.util import utcnow

    await repo.save_hltb_page(
        hltb_page.parse_page(
            _page(
                152017,
                comp_main=comp_main,
                release_world=f"{year}-06-01",
                profile_summary="The Master Chief returns.",
                **extra,
            )
        )  # type: ignore[arg-type]
    )
    old = (utcnow() - timedelta(days=days_ago)).isoformat(timespec="seconds")
    await repo._conn.execute("UPDATE hltb_entries SET page_read_at = ?", (old,))
    await repo.set_hltb_summary_ru(152017, "Мастер Чиф возвращается.", None)


def _fake_pages(monkeypatch, reads: list[int], data: dict | Exception | None) -> None:
    from bot.services.stores import hltb_page

    async def fetch(hltb_id: int):
        reads.append(hltb_id)
        if isinstance(data, Exception):
            raise data
        return data

    monkeypatch.setattr(hltb_page, "fetch_page", fetch)


async def test_an_entry_never_read_is_read_and_kept(repo: Repo, monkeypatch) -> None:
    from bot.services import hltb

    reads: list[int] = []
    _fake_pages(
        monkeypatch,
        reads,
        _page(
            7,
            comp_main=40680,
            release_world="2021-12-08",
            profile_genre="Shooter",
            profile_summary="The Master Chief returns.",
        ),
    )
    first = await hltb.resolve(repo, 7)
    second = await hltb.resolve(repo, 7)
    assert (first.main_hours, first.genre, first.release_year) == (11.3, "Shooter", 2021)
    assert second.main_hours == 11.3 and reads == [7]  # read once, then the mirror's
    assert first.game_url == "https://howlongtobeat.com/game/7"
    assert first.description_en == "The Master Chief returns."
    assert first.description_ru is None  # no key: English, to be translated later


async def test_a_young_games_times_are_read_again_once_stale(repo: Repo, monkeypatch) -> None:
    from bot.services import hltb

    await _store(repo, comp_main=0, year=2026, days_ago=4)
    reads: list[int] = []
    _fake_pages(
        monkeypatch,
        reads,
        _page(
            152017,
            comp_main=40680,
            release_world="2026-06-01",
            profile_summary="The Master Chief returns.",
        ),
    )

    async def no_translation(text, auth):
        raise AssertionError("the same summary keeps its translation")

    monkeypatch.setattr(hltb, "_translate", no_translation)

    got = await hltb.resolve(repo, 152017)
    assert reads == [152017]
    assert got.main_hours == 11.3
    assert got.description_ru == "Мастер Чиф возвращается."
    # Just read: trusted again, no request.
    await hltb.resolve(repo, 152017)
    assert reads == [152017]


async def test_a_settled_game_is_trusted_and_a_failed_re_read_keeps_the_stored(
    repo: Repo, monkeypatch
) -> None:
    from bot.services import hltb

    reads: list[int] = []
    _fake_pages(monkeypatch, reads, RuntimeError("HLTB is down"))
    await _store(repo, comp_main=43200, year=2015, days_ago=30)
    assert (await hltb.resolve(repo, 152017)).main_hours == 12.0  # no read at all
    assert reads == []

    await _store(repo, comp_main=0, year=2026, days_ago=10)
    got = await hltb.resolve(repo, 152017)
    assert reads == [152017]  # tried, and failed
    assert got.name == "Gears of War: E-Day" and got.main_hours is None
    # Nothing stored and HLTB down: an expected failure.
    import pytest

    with pytest.raises(hltb.HltbError):
        await hltb.resolve(repo, 999)


async def test_a_summary_is_translated_once_and_again_only_when_it_changes(
    repo: Repo, monkeypatch
) -> None:
    from bot.services import hltb
    from bot.services.stores import hltb_page

    await _store(repo, comp_main=43200, year=2015, days_ago=1)
    await repo._conn.execute("UPDATE hltb_entries SET summary_ru = NULL, summary_ru_of = NULL")
    await repo._conn.commit()
    paid: list[str] = []

    async def translate(text, auth):
        paid.append(text)
        return "перевод: " + text

    monkeypatch.setattr(hltb, "_translate", translate)
    auth = object()  # any: the translation is faked

    first = await hltb.resolve(repo, 152017, anthropic_auth=auth)  # type: ignore[arg-type]
    again = await hltb.resolve(repo, 152017, anthropic_auth=auth)  # type: ignore[arg-type]
    assert first.description_ru == again.description_ru == "перевод: The Master Chief returns."
    assert paid == ["The Master Chief returns."]  # paid for once

    # HLTB changes its summary: the translation is of the old text, so it is paid again.
    await repo.save_hltb_page(
        hltb_page.parse_page(_page(152017, profile_summary="A new story."))  # type: ignore[arg-type]
    )
    changed = await hltb.resolve(repo, 152017, anthropic_auth=auth)  # type: ignore[arg-type]
    assert changed.description_ru == "перевод: A new story."
    assert paid == ["The Master Chief returns.", "A new story."]


async def test_a_translation_made_before_its_text_was_known_goes_with_that_text(
    repo: Repo,
) -> None:
    """The cache's translations come over with no mark of what they translate:
    they are of the English text there then."""
    from bot.services.stores import hltb_page

    await _store(repo, comp_main=43200, year=2015, days_ago=1)  # a legacy translation, no mark
    await repo.save_hltb_page(
        hltb_page.parse_page(_page(152017, profile_summary="A new story."))  # type: ignore[arg-type]
    )
    row = await repo.hltb_entry(152017)
    assert row is not None
    assert result_from_entry(row).description_ru is None  # not of the new text


def test_an_entry_is_a_result_and_its_details_come_from_its_columns() -> None:
    row = {
        "hltb_id": 42,
        "name": "A Game",
        "release_year": 2020,
        "comp_main": 18000,
        "comp_main_med": 17000,
        "comp_plus": 0,
        "comp_100": 54000,
        "platforms": ["PS5"],
        "genres": "Adventure, Puzzle",
        "summary_en": "A game about a game.",
        "summary_ru": "Игра про игру.",
        "summary_ru_of": None,
        "review_score": 84,
        "developer": "Studio",
        "alias": "AGAG",
        "release_world": "2020-05-01",
        "release_eu": "2020-05-02",
        "comp_lvl_sp": 1,
        "comp_lvl_co": 0,
        "invested_co": 3600,
        "comp_speed_min": 7200,
        "count_backlog": 99,
    }
    r = result_from_entry(row)
    assert (r.hltb_id, r.name, r.release_year) == (42, "A Game", 2020)
    assert (r.main_hours, r.extra_hours, r.completionist_hours) == (5.0, None, 15.0)
    assert r.platforms == ["PS5"] and r.genre == "Adventure, Puzzle"
    assert r.game_url == "https://howlongtobeat.com/game/42"
    assert (r.description_en, r.description_ru) == ("A game about a game.", "Игра про игру.")
    assert r.details == {
        "review_score": 84,
        "developer": "Studio",
        "alias": "AGAG",
        "releases": {"world": "2020-05-01", "eu": "2020-05-02"},
        "modes": ["single"],
        # Co-op hours only count when the game is played that way; the users'
        # counts (count_backlog) are not sent.
        "times": {
            "main": {"average": 5.0, "median": 4.7},
            "completionist": {"average": 15.0},
        },
        "speedrun": {"any": {"best": 2.0}},
    }
    assert details_of_entry({"name": "Obscure"}) == {}
