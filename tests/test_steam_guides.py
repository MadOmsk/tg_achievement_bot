"""Tips from the Steam community's guides: what counts as a tip, and what does not."""

from __future__ import annotations

from bot.services import steam_guides as g

PAGE = """
<html><body>
<div class="workshopItemTitle">100% Achievement Guide</div>
<div class="guide subSections">
  <div class="subSectionTitle">Story</div>
  <div class="subSectionDesc">
    Get some!<br>Fire at least 150 rounds in one burst, killing at least 10 enemies.<br>
    The easiest method involves a machine gun on a bug mission.<br>
    Relentless<br>Finish a hunt in 30 seconds<br>
    Easiest to do on a new save file. Be ready with bear traps and guns.<br>
    Ending Achievements<br>Achievement<br>Description<br>How to unlock<br>
    Doing your part<br>Complete at least 100 missions.<br>
  </div>
</div>
<div class="commentthread_area">comments</div>
</body></html>
"""

CATALOG = [
    g.Wanted(("Get some!",), ("Fire at least 150 rounds in one burst",)),
    g.Wanted(("Relentless",), ("Finish a hunt in 30 seconds",)),
    g.Wanted(("Doing your part",), ("Complete at least 100 missions.",)),
]


def _guide() -> g.Guide:
    return g.make_guide("1", "100% Achievement Guide", g.guide_lines(PAGE))


def test_guide_lines_keep_the_guide_and_drop_the_page_around_it() -> None:
    lines = g.guide_lines(PAGE)
    assert "Get some!" in lines
    assert "comments" not in lines


def test_a_tip_is_the_advice_under_the_name() -> None:
    tip = g.tip_for([_guide()], CATALOG[0], g.everything_named(CATALOG))
    assert tip is not None
    assert "machine gun" in tip.text
    assert tip.guide_id == "1"


def test_the_description_and_trailing_table_headings_are_not_a_tip() -> None:
    tip = g.tip_for([_guide()], CATALOG[1], g.everything_named(CATALOG))
    assert tip is not None
    assert tip.text.startswith("Easiest to do on a new save file.")
    assert "Finish a hunt" not in tip.text
    for heading in ("Ending Achievements", "Description", "How to unlock"):
        assert heading not in tip.text


def test_a_guide_that_only_repeats_the_description_gives_no_tip() -> None:
    assert g.tip_for([_guide()], CATALOG[2], g.everything_named(CATALOG)) is None


def test_a_guide_mostly_in_ideographs_is_passed_over() -> None:
    assert g._mostly_ideographs("全成就攻略", ["完成战役 收集全部头骨"] * 10)
    assert not g._mostly_ideographs("100% guide", ["Complete the mission"] * 10)
    assert not g._mostly_ideographs("Гайд", ["Пройдите миссию"] * 10)


def test_links_and_embedded_videos_are_kept_as_addresses() -> None:
    page = (
        '<div class="guide subSections"><div>'
        'Watch <a class="bb_link" href="https://www.youtube.com/watch?v=OdlHgtKy3Wk">this</a>.<br>'
        '<div class="sharedFilePreviewYouTubeVideo sizeFull" id="t8d_J46g6Po"></div>'
        '<a href="https://example.com/x">https://example.com/x</a>'
        "</div></div>"
    )
    assert g.guide_lines(page) == [
        "Watch [this](https://www.youtube.com/watch?v=OdlHgtKy3Wk).",
        "https://www.youtube.com/watch?v=t8d_J46g6Po",
        "https://example.com/x",
    ]


def test_a_long_tip_is_kept_whole_and_ends_at_the_next_section() -> None:
    advice = [f"Step {i}: do this part of the run carefully and then move on." for i in range(20)]
    lines = ["Long One", *advice, "Benefits", "Unrelated text about something else."]
    guide = g.make_guide("1", "t", lines)
    tip = g.tip_for([guide], g.Wanted(("Long One",)), {"long one"})
    assert tip is not None
    assert tip.text.count("\n") == 19
    assert "Benefits" not in tip.text
