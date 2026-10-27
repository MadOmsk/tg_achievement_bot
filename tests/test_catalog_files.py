"""Labels and weights go between copies of the catalog by key, never by id."""

from __future__ import annotations

import pytest

from bot.db.repo import Repo
from bot.services import store_collect
from bot.services.store_collect import StoreCollector
from scripts import catalog_files


async def _version(repo: Repo, title_id: str, name: str) -> int:
    await repo.upsert_title(title_id, name, "xbox_360")
    report = store_collect.CollectReport("xbox_360", title_id)
    await StoreCollector(repo)._list_version("xbox_360", title_id, report)
    return report.versions[0]


async def test_a_label_and_the_weights_come_back_by_key(
    repo: Repo, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(catalog_files, "ROOT", tmp_path)
    monkeypatch.setattr(catalog_files, "LABELS", tmp_path / "labels.jsonl")
    monkeypatch.setattr(catalog_files, "WEIGHTS", tmp_path / "weights.json")
    a = await _version(repo, "1297287339", "Gears of War 3")
    b = await _version(repo, "1297287122", "Kameo")
    await repo.save_decision(
        a, b, "other", features=None, model=None, decided_by="viewer",
        decided_at="2026-10-01T00:00:00+00:00",
    )  # fmt: skip
    await repo.add_match_weights({"same": {"bias": -1.0}}, gate_before=0.5, gate_after=0.7,
                                 labels=1, activate=True)  # fmt: skip
    assert await catalog_files.export(repo) == (1, True)
    line = (tmp_path / "labels.jsonl").read_text("utf-8").strip()
    assert '"a": "xbox:1297287339:360"' in line and '"by": "viewer"' in line

    await repo.delete_decision(a, b)
    await repo.activate_match_weights(None)
    counts = await catalog_files.import_files(repo)
    assert counts == {"labels": 1, "set": 1, "unchanged": 0, "missing": 0, "weights": 1}
    [row] = await repo.decisions_among([a])
    assert (row["relation"], row["decided_by"], row["decided_at"]) == (
        "other", "viewer", "2026-10-01T00:00:00+00:00",
    )  # fmt: skip
    assert (await repo.active_match_weights())[1] == {"same": {"bias": -1.0}}
    # A second import changes nothing.
    again = await catalog_files.import_files(repo)
    assert (again["set"], again["unchanged"], again["weights"]) == (0, 1, 0)
