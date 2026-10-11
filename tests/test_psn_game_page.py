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


async def test_one_unknown_title_id_does_not_fail_the_whole_lookup(monkeypatch) -> None:
    """2026-10-11: a store page named a CUSA Sony never shipped, and the
    whole batch failed with NotFound; the others are asked one by one."""
    from types import SimpleNamespace

    from psnawp_api.core.psnawp_exceptions import PSNAWPNotFoundError

    from bot.services.psn import client as psn

    async def no_wait(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(psn, "_call", no_wait)

    def get(url: str, params: dict) -> SimpleNamespace:
        ids = params["npTitleIds"].split(",")
        if "BAD_00" in ids:
            raise PSNAWPNotFoundError("Resource not found")
        titles = [
            {"npTitleId": t, "trophyTitles": [{"npCommunicationId": "NPWR00001_00"}]} for t in ids
        ]
        return SimpleNamespace(json=lambda: {"titles": titles})

    fake = SimpleNamespace(authenticator=SimpleNamespace(get=get))
    found = await psn.trophy_lists_of(fake, "acc", ["CUSA1_00", "BAD_00", "CUSA2_00"])  # type: ignore[arg-type]
    assert found == {"CUSA1_00": {"NPWR00001_00"}, "CUSA2_00": {"NPWR00001_00"}}
