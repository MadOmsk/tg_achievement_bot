"""PSN descriptions: one owner, the game's whole trophy list (#50)."""

from __future__ import annotations

from bot.services.psn.client import EarnedTrophy
from scripts import backfill_descriptions as script

GAME = "NPWR38625_00"


def _trophy(trophy_id: int, detail: str) -> EarnedTrophy:
    return EarnedTrophy(
        trophy_id=trophy_id,
        title_name="Game",
        title_icon_url=None,
        trophy_name=f"T{trophy_id}",
        trophy_detail=detail,
        trophy_icon_url=None,
        trophy_type=None,  # type: ignore[arg-type]
        trophy_hidden=False,
        trophy_rarity=None,
        trophy_earn_rate=None,
        earned_date_time=None,
    )


class _Auth:
    async def get_client(self):
        return "en"

    async def get_translation_client(self):
        return "ru"


async def test_one_owner_answers_for_a_trophy_only_another_earned(monkeypatch) -> None:
    """Trophy 11 is only B's, but A's answer lists it too when asked for the
    whole list — so A is the only one asked."""
    asked: list[tuple[str, bool]] = []

    async def trophies_for_title(client, account_id, title, *, earned_only=True):
        if client == "en":
            asked.append((account_id, earned_only))
        return [_trophy(n, f"{client} {n}") for n in (1, 2, 11)]

    recorded: list[dict] = []

    async def record(repo, anthropic_auth, work, native, totals):
        recorded.append(native)

    monkeypatch.setattr(script, "trophies_for_title", trophies_for_title)
    monkeypatch.setattr(script, "_record", record)
    work = script.TitleWork("psn", GAME, {"2", "11"}, [(1, "acc-a"), (2, "acc-b")])
    titles = {acc: {GAME: object()} for acc in ("acc-a", "acc-b")}

    await script.run_psn(None, None, _Auth(), work, titles, script.Totals())  # type: ignore[arg-type]

    assert asked == [("acc-a", False)]
    assert recorded[0]["11"] == ("ru 11", "en 11")
