"""playstation.com's game page as a source of PSN title ids (#147)."""

from bot.services.stores.psn_store import page_slug, title_ids_on_page


def test_page_slug():
    assert page_slug("Grand Theft Auto V") == "grand-theft-auto-v"
    assert page_slug("Marvel’s Spider-Man: Miles Morales™") == "marvels-spider-man-miles-morales"


def test_title_ids_on_page():
    html = (
        '"UP1004-PPSA03420_00-GTAOSTANDALONE01" "CUSA00419" '
        '"UP1004-CUSA00419_00-GTAVDIGITALDOWNL" "PPSA16755"'
    )
    assert title_ids_on_page(html) == ["PPSA03420_00", "CUSA00419_00", "PPSA16755_00"]
