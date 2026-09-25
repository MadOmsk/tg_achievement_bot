"""PSN descriptions: every owner is asked until no trophy is missing (#50)."""

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


async def test_a_trophy_only_the_second_owner_earned_is_still_fetched(monkeypatch) -> None:
    earned = {"acc-a": [1, 2], "acc-b": [1, 11]}  # trophy 11 is only B's
    asked: list[str] = []

    async def trophies_for_title(client, account_id, title):
        if client == "en":
            asked.append(account_id)
        return [_trophy(n, f"{client} {n}") for n in earned[account_id]]

    recorded: list[set[str]] = []

    async def record(repo, anthropic_auth, work, native, totals):
        recorded.append(set(native))

    monkeypatch.setattr(script, "trophies_for_title", trophies_for_title)
    monkeypatch.setattr(script, "_record", record)
    work = script.TitleWork("psn", GAME, {"2", "11"}, [(1, "acc-a"), (2, "acc-b"), (3, "acc-c")])
    titles = {acc: {GAME: object()} for acc in ("acc-a", "acc-b", "acc-c")}

    await script.run_psn(None, None, _Auth(), work, titles, script.Totals())  # type: ignore[arg-type]

    assert recorded == [{"2"}, {"11"}]
    assert asked == ["acc-a", "acc-b"]  # C is never asked: nothing was left
