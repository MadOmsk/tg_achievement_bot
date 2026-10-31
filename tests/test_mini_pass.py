"""The season pass is judged by the server (owner, 2026-10-27): a theme or a
prize is claimed only with the month's points, a prize's code goes one to a
person, and the super-admin's edits are a draft nobody else sees until one
publish — never touching what somebody already has."""

from __future__ import annotations

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bot.config import Settings
from bot.db.repo import Repo
from bot.services import season_pass
from bot.services.notifier import carries
from bot.web.mini_api import cors_middleware, setup_mini_api
from tests.test_mini_game_person import _signed_init_data


async def _client(repo: Repo, settings: Settings, monkeypatch, tg_id: int, points: dict[str, int]):
    app = web.Application(middlewares=[cors_middleware()])
    setup_mini_api(app, settings, repo)
    await repo.ensure_user(tg_id, f"p{tg_id}")
    headers = {
        "X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), tg_id)
    }

    async def fake_points(person_id, since, until=None):
        return points["n"]

    monkeypatch.setattr(repo, "points_for_person", fake_points)
    client = TestClient(TestServer(app))
    await client.start_server()
    return client, headers


async def test_a_theme_is_claimed_only_with_the_points(
    repo: Repo, settings: Settings, monkeypatch
) -> None:
    points = {"n": 0}
    client, headers = await _client(repo, settings, monkeypatch, 42, points)
    person = await repo.person_id(42)
    try:
        state = await (await client.get("/api/mini/pass", headers=headers)).json()
        # The pass starts from the app's themes, nothing claimed.
        assert [t["palette"] for t in state["tiers"]] == [
            p for p, _, _ in season_pass.DEFAULT_THEMES
        ]
        assert not any(t["claimed"] for t in state["tiers"])

        claim = {"palette": "graphite"}
        assert (
            await client.post("/api/mini/pass/claim", json=claim, headers=headers)
        ).status == 403
        points["n"] = 160
        assert (
            await client.post("/api/mini/pass/claim", json=claim, headers=headers)
        ).status == 200
        assert await repo.pass_claims(person) == {"graphite"}
        late = {"palette": "rose"}
        assert (await client.post("/api/mini/pass/claim", json=late, headers=headers)).status == 403
        assert (
            await client.post("/api/mini/pass/claim", json={"palette": "violet"}, headers=headers)
        ).status == 400
        # Only the super-admin edits the pass.
        prize = {"kind": "code", "title": "Key", "points": 0, "codes": ["A"]}
        assert (
            await client.post("/api/mini/pass/items", json=prize, headers=headers)
        ).status == 403
    finally:
        await client.close()


async def test_a_draft_shows_once_published_and_what_is_claimed_stays(repo: Repo) -> None:
    await repo.ensure_pass_seeded(season_pass.DEFAULT_THEMES)
    people = []
    for tg_id in (51, 52, 53):
        await repo.ensure_user(tg_id, f"p{tg_id}")
        people.append(await repo.person_id(tg_id))

    prize = await repo.add_pass_item(
        {"kind": "code", "title": "Game key", "points": 0}, ["AAA", "BBB"], None
    )
    # A draft: nobody sees it yet.
    assert all(i["kind"] == "theme" for i in await repo.pass_live_items(people[0]))
    result = await repo.publish_pass()
    assert result["added"] == ["Game key"]

    assert await repo.claim_pass_code(prize, people[0]) == "AAA"
    # A second tap gives the same code, never a second one.
    assert await repo.claim_pass_code(prize, people[0]) == "AAA"
    assert await repo.claim_pass_code(prize, people[1]) == "BBB"
    assert await repo.claim_pass_code(prize, people[2]) is None

    # A change to a level somebody has is left out at the publish.
    await repo.edit_pass_item(prize, {"title": "Another"}, None)
    result = await repo.publish_pass()
    assert result["skipped"] == 1
    assert (await repo.pass_item(prize))["title"] == "Game key"

    # An unclaimed published level waits for the publish to change or go.
    theme = next(i for i in await repo.pass_editor_items() if i["palette"] == "rose")
    await repo.edit_pass_item(theme["item_id"], {"points": 2000}, None)
    assert (await repo.pass_item(theme["item_id"]))["points"] == 1600
    await repo.publish_pass()
    assert (await repo.pass_item(theme["item_id"]))["points"] == 2000
    await repo.remove_pass_item(theme["item_id"])
    await repo.publish_pass()
    assert "rose" not in {i["palette"] for i in await repo.pass_live_items(people[2])}

    # A draft thrown away leaves the pass as it was.
    await repo.add_pass_item({"kind": "code", "title": "Later", "points": 5}, ["C"], None)
    await repo.discard_pass_draft()
    assert all(
        not i["draft"]
        for i in [{"draft": r["state"] == "draft"} for r in await repo.pass_editor_items()]
    )


def test_reward_notices_are_on_until_switched_off() -> None:
    assert carries(frozenset(), "pass_reward", {}, friend=False)
    assert not carries(frozenset({"pass_reward:off"}), "pass_reward", {}, friend=False)
    # Every other kind stays opt-in.
    assert not carries(frozenset(), "new_follower", {}, friend=False)


async def test_a_prize_keeps_its_platform(repo: Repo) -> None:
    item = await repo.add_pass_item(
        {"kind": "code", "title": "Hades", "points": 5, "platform": "Steam"}, ["A"], None
    )
    await repo.edit_pass_item(item, {"platform": "Xbox 360"}, None)
    rows = {r["item_id"]: r for r in await repo.pass_editor_items()}
    assert rows[item]["platform"] == "Xbox 360"
    await repo.publish_pass()
    assert (await repo.pass_item(item))["platform"] == "Xbox 360"


async def test_a_prizes_takers_are_listed_without_their_codes(repo: Repo) -> None:
    item = await repo.add_pass_item(
        {"kind": "code", "title": "Hades", "points": 0}, ["A", "B"], None
    )
    await repo.publish_pass()
    await repo.ensure_user(501, "taker")
    taker = await repo.person_id(501)
    assert await repo.claim_pass_code(item, taker) == "A"
    takers = await repo.pass_item_takers(item)
    assert [t["person_id"] for t in takers] == [taker]
    assert "code" not in takers[0]


async def test_every_month_has_a_pass_of_its_own(
    repo: Repo, settings: Settings, monkeypatch
) -> None:
    from bot.web.mini_pass import _next_month, _previous_month

    points = {"n": 500}
    client, headers = await _client(repo, settings, monkeypatch, 43, points)
    person = await repo.person_id(43)
    try:
        now = (await (await client.get("/api/mini/pass", headers=headers)).json())["month"]
        before, after = _previous_month(now), _next_month(now)
        old = await repo.add_pass_item(
            {"kind": "code", "title": "Old", "points": 10}, ["OLD1", "OLD2"], None, before
        )
        ahead = await repo.add_pass_item(
            {"kind": "code", "title": "Ahead", "points": 10}, ["NEW"], None, after
        )
        await repo.publish_pass(before)
        await repo.publish_pass(after)
        await repo.claim_pass_code(old, person)

        state = await (await client.get("/api/mini/pass", headers=headers)).json()
        # This month shows neither the last month's nor the next one's levels.
        assert {r["id"] for r in state["rewards"]}.isdisjoint({old, ahead})
        assert state["current"] and before in state["months"] and after not in state["months"]

        back = await (await client.get(f"/api/mini/pass?month={before}", headers=headers)).json()
        assert not back["current"]
        assert next(r for r in back["rewards"] if r["id"] == old)["code"] == "OLD1"
        # An earlier month's prize is only looked back on, never taken.
        late = await client.post(f"/api/mini/pass/items/{old}/claim", headers=headers)
        assert late.status == 403
        # A month still to come is never shown early.
        early = await (await client.get(f"/api/mini/pass?month={after}", headers=headers)).json()
        assert early["month"] == now
    finally:
        await client.close()


async def test_a_pass_name_waits_for_the_publish(repo: Repo) -> None:
    await repo.set_pass_season_title("2026-11", "Halloween")
    season = await repo.pass_season("2026-11")
    assert season["title"] is None and season["draft_title"] == "Halloween"
    assert (await repo.pass_month_counts(["2026-11"]))["2026-11"]["dirty"] == 1
    await repo.publish_pass("2026-11")
    assert (await repo.pass_season("2026-11"))["title"] == "Halloween"
    await repo.set_pass_season_title("2026-11", None)
    await repo.discard_pass_draft("2026-11")
    assert (await repo.pass_season("2026-11"))["title"] == "Halloween"


async def test_a_pass_cover_waits_for_the_publish(repo: Repo) -> None:
    await repo.set_pass_season_title("2026-12", "Winter")
    assert await repo.set_pass_season_image("2026-12", "a.jpg") is None
    season = await repo.pass_season("2026-12")
    assert season["image_path"] is None and season["draft_image_path"] == "a.jpg"
    assert season["draft_title"] == "Winter"
    # A second draft picture leaves the first unused, to delete.
    assert await repo.set_pass_season_image("2026-12", "b.jpg") == "a.jpg"
    await repo.publish_pass("2026-12")
    season = await repo.pass_season("2026-12")
    assert season["image_path"] == "b.jpg" and season["title"] == "Winter"
    await repo.set_pass_season_image("2026-12", "c.jpg")
    assert await repo.discard_pass_draft("2026-12") == ["c.jpg"]
    assert (await repo.pass_season("2026-12"))["image_path"] == "b.jpg"


def test_level_notices_carry_every_level_or_only_prizes() -> None:
    assert carries(frozenset(), "pass_level", {"prize": False}, friend=False)
    only = frozenset({"pass_level:prizes"})
    assert not carries(only, "pass_level", {"prize": False}, friend=False)
    assert carries(only, "pass_level", {"prize": True}, friend=False)
    assert not carries(frozenset({"pass_level:off"}), "pass_level", {"prize": True}, friend=False)


async def test_a_level_reached_is_told_once_a_month(repo: Repo, monkeypatch) -> None:
    from cryptography.fernet import Fernet

    from bot.services.crypto import TokenCipher
    from bot.services.notifier import Notifier

    await repo.ensure_user(77, "p77")
    person = await repo.person_id(77)
    from bot.util import utcnow

    await repo.ensure_pass_seeded(season_pass.DEFAULT_THEMES, utcnow().strftime("%Y-%m"))
    told: list[tuple[str, dict]] = []

    async def fake_notify(recipient, kind, *, friend=False, **data):
        told.append((kind, data))

    points = {"n": 100}

    async def fake_points(person_id, since, until=None):
        return points["n"]

    monkeypatch.setattr(repo, "points_for_person", fake_points)
    notifier = Notifier(repo, TokenCipher(Fernet.generate_key().decode()))
    monkeypatch.setattr(notifier, "notify", fake_notify)

    await notifier.tell_about_pass_levels(person)
    assert told == []
    # Two levels at once are one notice, of the higher.
    points["n"] = 450
    await notifier.tell_about_pass_levels(person)
    assert [(k, d["palette"], d["count"], d["prize"]) for k, d in told] == [
        ("pass_level", "ocean", 2, False)
    ]
    await notifier.tell_about_pass_levels(person)
    assert len(told) == 1


def test_a_prize_picture_is_saved_again_as_a_jpeg() -> None:
    import io

    from PIL import Image

    from bot.services import pass_pictures

    raw = io.BytesIO()
    Image.new("RGB", (3000, 1500), (200, 40, 90)).save(raw, format="PNG")
    picture = pass_pictures.normalize(raw.getvalue())
    assert picture is not None
    with Image.open(io.BytesIO(picture)) as image:
        assert image.format == "JPEG" and max(image.size) == pass_pictures.SIDE
    assert pass_pictures.normalize(b"not a picture") is None


async def test_a_draft_picture_shows_only_through_the_editors_address(
    repo: Repo, settings: Settings, monkeypatch, tmp_path
) -> None:
    import io

    from PIL import Image

    from bot.services import pass_pictures
    from bot.web.mini_pass import _picture

    monkeypatch.chdir(tmp_path)
    client, _headers = await _client(repo, settings, monkeypatch, 44, {"n": 0})
    try:
        item = await repo.add_pass_item({"kind": "code", "title": "Soon", "points": 5}, ["A"], None)
        raw = io.BytesIO()
        Image.new("RGB", (64, 64), (10, 20, 30)).save(raw, format="PNG")
        path = await pass_pictures.store(item, raw.getvalue())
        await repo.edit_pass_item(item, {"image_path": path}, None)

        signed = _picture(item, path, draft=True)
        plain = _picture(item, path)
        assert signed is not None and plain is not None
        # Nobody guesses a prize before it is published, nor its waiting picture.
        assert (await client.get(plain)).status == 404
        assert (await client.get(plain + "&draft=1")).status == 404
        assert (await client.get(signed.replace("&s=", "&s=0"))).status == 404
        assert (await client.get(signed)).status == 200
    finally:
        await client.close()


async def test_roles_open_the_editor_and_only_a_superadmin_gives_them(
    repo: Repo, settings: Settings, monkeypatch
) -> None:
    admin_tg = settings.superadmin_tg_ids[0]
    client, headers = await _client(repo, settings, monkeypatch, admin_tg, {"n": 0})
    await repo.ensure_superadmins([admin_tg])
    await repo.ensure_user(601, "helper")
    helper = await repo.person_id(601)
    helper_headers = {
        "X-Telegram-Init-Data": _signed_init_data(settings.bot_token.get_secret_value(), 601)
    }
    try:
        me = await (await client.get("/api/mini/me", headers=headers)).json()
        assert me["role"] == "superadmin"
        # An ordinary person edits nothing and gives nothing.
        state = await (await client.get("/api/mini/pass", headers=helper_headers)).json()
        assert not state["admin"]

        def step(target: int, action: str, n: int) -> dict:
            return {"scope": "user", "target": f"p{target}", "action": action, "step": n}

        res = await client.post(
            "/api/mini/admin/actions", json=step(helper, "make_admin", 0), headers=helper_headers
        )
        assert res.status == 403
        # The super-admin makes them an admin, one step and confirmed, as the
        # bot's card does: the editor opens, roles stay shut.
        res = await client.post(
            "/api/mini/admin/actions", json=step(helper, "make_admin", 0), headers=headers
        )
        confirm = (await res.json())["confirm"]
        res = await client.post(
            "/api/mini/admin/actions",
            json=step(helper, "make_admin", confirm["step"]),
            headers=headers,
        )
        assert (await res.json())["done"]["ok"]
        assert await repo.person_role(helper) == "admin"
        state = await (await client.get("/api/mini/pass", headers=helper_headers)).json()
        assert state["admin"]
        # No jump past a step: user → super-admin is no action at all.
        role = await (
            await client.get(f"/api/mini/admin/users/p{helper}/role", headers=headers)
        ).json()
        assert role["role"] == "admin"
        me_id = await repo.person_id(admin_tg)
        res = await client.post(
            "/api/mini/admin/actions",
            json=step(me_id, "unmake_superadmin", 1),
            headers=helper_headers,
        )
        assert res.status == 403 or not (await res.json())["done"]["ok"]
        assert await repo.person_role(me_id) == "superadmin"
    finally:
        await client.close()


async def test_only_the_pass_s_own_page_counts_as_seen(
    repo: Repo, settings: Settings, monkeypatch
) -> None:
    client, headers = await _client(repo, settings, monkeypatch, 42, {"n": 0})
    person = await repo.person_id(42)
    try:
        state = await (await client.get("/api/mini/pass", headers=headers)).json()
        month = state["month"]
        assert not await repo.pass_seen_in(person, month)
        assert (await client.post("/api/mini/pass/seen", headers=headers)).status == 200
        assert await repo.pass_seen_in(person, month)
    finally:
        await client.close()
