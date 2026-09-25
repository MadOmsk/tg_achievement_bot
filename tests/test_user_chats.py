"""Panel's "Мои чаты" (SPEC 6.2): every chat a person has touched, and
"delete" as a reset back to never-touched-it."""

from __future__ import annotations

from pathlib import Path

from bot.db.repo import Repo

MIGRATION_063 = Path("bot/db/migrations/063_rarity_to_person_digest_to_chat.sql").read_text(
    encoding="utf-8"
)

TG_ID = 1
CHAT_A = -100501
CHAT_B = -100502


async def render_chat_card(repo: Repo, chat_id: int, title: str) -> None:
    await repo.upsert_chat(chat_id, title, TG_ID)


async def test_subscribed_chat_is_listed_as_subscribed(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Гейминг-чат")
    await repo.subscribe(CHAT_A, TG_ID)

    chats = await repo.user_chats(TG_ID)

    assert len(chats) == 1
    assert chats[0].chat_id == CHAT_A
    assert chats[0].is_subscribed is True


async def test_only_seen_chat_is_listed_as_not_subscribed(repo: Repo) -> None:
    """chat_seen alone (never subscribed) still counts as "known" (SPEC 6.3's
    membership definition), just not publishing there."""
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Гейминг-чат")
    await repo.record_chat_seen(CHAT_A, TG_ID)

    chats = await repo.user_chats(TG_ID)

    assert len(chats) == 1
    assert chats[0].is_subscribed is False


async def test_untouched_chat_does_not_appear(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Гейминг-чат")
    # Neither subscribed nor seen — must not show up.
    assert await repo.user_chats(TG_ID) == []


async def test_inactive_chat_is_excluded(repo: Repo) -> None:
    """A chat the bot got kicked from — nothing left to manage there."""
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Гейминг-чат")
    await repo.subscribe(CHAT_A, TG_ID)
    await repo.set_chat_active(CHAT_A, False)

    assert await repo.user_chats(TG_ID) == []


async def test_unsubscribe_keeps_the_chat_listed(repo: Repo) -> None:
    """Unsubscribing only removes the publishing row — chat_seen (and so the
    chat's place in this list) stays, one tap away from re-subscribing."""
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Гейминг-чат")
    await repo.subscribe(CHAT_A, TG_ID)
    await repo.record_chat_seen(CHAT_A, TG_ID)

    await repo.unsubscribe(CHAT_A, TG_ID)

    chats = await repo.user_chats(TG_ID)
    assert len(chats) == 1
    assert chats[0].is_subscribed is False


async def test_forget_chat_membership_removes_it_from_the_list(repo: Repo) -> None:
    """ "Delete" (SPEC 6.2) clears both subscriptions and chat_seen — the
    chat vanishes from the list entirely, as if never touched."""
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Гейминг-чат")
    await repo.subscribe(CHAT_A, TG_ID)
    await repo.record_chat_seen(CHAT_A, TG_ID)

    await repo.forget_chat_membership(CHAT_A, TG_ID)

    assert await repo.user_chats(TG_ID) == []
    assert await repo.is_subscribed(CHAT_A, TG_ID) is False


async def test_forget_chat_membership_is_not_a_ban(repo: Repo) -> None:
    """Re-subscribing (or being seen writing again) after "delete" brings the
    chat right back — no third, blocked state (SPEC 6.2: "банов тут нету")."""
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Гейминг-чат")
    await repo.subscribe(CHAT_A, TG_ID)
    await repo.forget_chat_membership(CHAT_A, TG_ID)

    await repo.subscribe(CHAT_A, TG_ID)

    chats = await repo.user_chats(TG_ID)
    assert len(chats) == 1
    assert chats[0].is_subscribed is True


async def test_a_new_person_starts_from_the_admin_default_mode(repo: Repo) -> None:
    """The rarity mode is the person's since #126, and the admin's default
    for new people (app_settings['default_rarity_mode']) moved with it."""
    await repo.set_app_setting("default_rarity_mode", "rare")
    await repo.ensure_user(TG_ID, "igor")

    settings_row = await repo.get_user_settings(TG_ID)

    assert settings_row is not None and settings_row.rarity_mode == "rare"


async def test_the_mode_is_one_for_every_chat(repo: Repo) -> None:
    """Somebody in many chats sets it once (#126)."""
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Чат А")
    await render_chat_card(repo, CHAT_B, "Чат Б")
    await repo.subscribe(CHAT_A, TG_ID)
    await repo.subscribe(CHAT_B, TG_ID)

    await repo.update_user_settings(TG_ID, rarity_mode="rare")

    targets = {t.chat_id: t.rarity_mode for t in await repo.publication_targets(TG_ID)}
    assert targets == {CHAT_A: "rare", CHAT_B: "rare"}


async def test_the_digest_size_is_the_chats(repo: Repo) -> None:
    """Set by the chat's admin (#126), the same for everybody publishing there."""
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Чат А")
    await render_chat_card(repo, CHAT_B, "Чат Б")
    await repo.subscribe(CHAT_A, TG_ID)
    await repo.subscribe(CHAT_B, TG_ID)

    await repo.update_chat_settings(CHAT_A, digest_threshold=5)

    targets = {t.chat_id: t.digest_threshold for t in await repo.publication_targets(TG_ID)}
    assert targets == {CHAT_A: 5, CHAT_B: 3}


async def test_migration_063_moves_the_mode_to_the_person_and_the_digest_to_the_chat(
    tmp_path,
) -> None:
    import aiosqlite

    sql = MIGRATION_063
    async with aiosqlite.connect(tmp_path / "m063.db") as conn:
        await conn.executescript(
            """
            CREATE TABLE user_settings (tg_id INTEGER PRIMARY KEY);
            CREATE TABLE chat_settings (chat_id INTEGER PRIMARY KEY);
            CREATE TABLE subscriptions (
                chat_id INTEGER, tg_id INTEGER, created_at TEXT,
                rarity_mode TEXT NOT NULL DEFAULT 'all'
                    CHECK (rarity_mode IN ('all', 'rare', 'hidden')),
                digest_threshold INTEGER NOT NULL DEFAULT 3,
                PRIMARY KEY (chat_id, tg_id));
            INSERT INTO user_settings VALUES (1), (2), (3);
            INSERT INTO chat_settings VALUES (-1), (-2);
            INSERT INTO subscriptions VALUES
                (-1, 1, 'x', 'rare', 3), (-2, 1, 'x', 'rare', 5),
                (-1, 2, 'x', 'hidden', 3), (-2, 2, 'x', 'all', 99);
            """
        )
        await conn.executescript(sql)
        modes = dict(
            await (await conn.execute("SELECT tg_id, rarity_mode FROM user_settings")).fetchall()
        )
        digests = dict(
            await (
                await conn.execute("SELECT chat_id, digest_threshold FROM chat_settings")
            ).fetchall()
        )
        columns = [
            r[1] for r in await (await conn.execute("PRAGMA table_info(subscriptions)")).fetchall()
        ]

    assert modes == {1: "rare", 2: "all", 3: "all"}  # a tie goes to the more permissive
    assert digests == {-1: 3, -2: 5}  # a tie goes to the smaller
    assert columns == ["chat_id", "tg_id", "created_at"]


async def test_multiple_chats_are_all_listed(repo: Repo) -> None:
    await repo.ensure_user(TG_ID, "igor")
    await render_chat_card(repo, CHAT_A, "Чат А")
    await render_chat_card(repo, CHAT_B, "Чат Б")
    await repo.subscribe(CHAT_A, TG_ID)
    await repo.record_chat_seen(CHAT_B, TG_ID)

    chats = {c.chat_id: c.is_subscribed for c in await repo.user_chats(TG_ID)}

    assert chats == {CHAT_A: True, CHAT_B: False}
