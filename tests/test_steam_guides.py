"""Reading a Steam guide page as lines, and taking a tip out of the lines a model chose."""

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


def _guide() -> g.Guide:
    return g.make_guide("1", "100% Achievement Guide", g.guide_lines(PAGE))


def test_guide_lines_keep_the_guide_and_drop_the_page_around_it() -> None:
    lines = g.guide_lines(PAGE)
    assert "Get some!" in lines
    assert "comments" not in lines


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


def test_a_table_row_is_one_line_its_cells_joined() -> None:
    page = (
        '<div class="guide subSections"><table class="bb_table">'
        "<tr><td>Artifact</td><td>Anomaly type</td><td>Rarity</td></tr>"
        "<tr><td>Battery</td><td>Electro</td><td>Common</td></tr></table>After.</div>"
    )
    assert g.guide_lines(page) == [
        "Artifact \u00a6 Anomaly type \u00a6 Rarity",
        "Battery \u00a6 Electro \u00a6 Common",
        "After.",
    ]


def test_pictures_videos_and_bare_links_alone_are_no_tip() -> None:
    pictures = (
        "https://images.steamusercontent.com/ugc/1/AA/\nhttps://www.youtube.com/watch?v=OdlHgtKy3Wk"
    )
    assert not g.has_prose(pictures)
    assert not g.has_prose("[a link](https://example.com/x)")
    assert g.has_prose(pictures + "\nSwim into the school of fish fifteen times to get it.")

    lines = ["Kraken", "https://images.steamusercontent.com/ugc/1/AA/"]
    guide = g.make_guide("1", "t", lines + ["x"] * 10)
    assert g.tip_from_lines(guide, [(0, 1)]) is None


def test_steams_link_filter_is_unwrapped() -> None:
    page = (
        '<div class="guide subSections"><div class="subSectionContent">'
        '<a href="https://steamcommunity.com/linkfilter/?u=https%3A%2F%2Fmapgenie.io%2Fmap">map</a>'
        "</div></div>"
    )
    assert "[map](https://mapgenie.io/map)" in "\n".join(g.guide_lines(page))


def test_steams_div_tables_are_rows_of_cells() -> None:
    page = (
        '<div class="guide subSections"><div class="subSectionContent">Below:<br>'
        '<div class="bb_table"><div class="bb_table_tr"><div class="bb_table_th">Artifact</div>'
        '<div class="bb_table_th">Rarity</div></div><div class="bb_table_tr">'
        '<div class="bb_table_td">Battery</div><div class="bb_table_td">Common</div></div>'
        "</div></div></div>"
    )
    assert g.guide_lines(page) == ["Below:", "Artifact ¦ Rarity", "Battery ¦ Common"]


def test_destroyed_apostrophes_are_repaired() -> None:
    page = (
        '<div class="guide subSections"><div class="subSectionContent">'
        "If you\ufffd\ufffd\ufffdve finished, it hasn\ufffd\ufffd\ufffdt unlocked \ufffd yet."
        "</div></div>"
    )
    assert g.guide_lines(page) == ["If you\u2019ve finished, it hasn\u2019t unlocked yet."]


def test_pieces_of_a_section_are_joined_without_what_lies_between() -> None:
    lines = [
        "Scanning complete",
        "Welcome to the guide! Thank you for reading.",
        "There are ten scanners in total; each is found once.",
        "This guide is translated with Google Translate, #StandWithUkraine",
        "The first is in Garbage, north of the depot.",
    ]
    guide = g.make_guide("1", "t", lines + ["x"] * 10)
    text = g.tip_from_lines(guide, [(2, 2), (4, 4)])
    assert text == (
        "There are ten scanners in total; each is found once.\n"
        "The first is in Garbage, north of the depot."
    )


def test_the_guides_kept_in_memory_age_out_and_are_bounded(monkeypatch) -> None:
    monkeypatch.setattr(g, "_guide_memory", g.OrderedDict())
    monkeypatch.setattr(g, "_DISK_DIR", g.Path("no-such-dir-for-tests"))
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(g.time, "time", lambda: now["t"])

    g._keep("old", g.make_guide("old", "t", ["x"]), now["t"])
    assert g._recall("old")[0] is True
    now["t"] += g._DISK_SECONDS + 1
    assert g._recall("old") == (False, None)
    assert "old" not in g._guide_memory

    for i in range(g._MEMORY_GUIDES + 5):
        g._keep(str(i), None, now["t"])
    assert len(g._guide_memory) == g._MEMORY_GUIDES
    assert "0" not in g._guide_memory
