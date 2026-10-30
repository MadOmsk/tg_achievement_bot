"""Who may do what (#232): the four roles, the chat admin's life, publishing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from bot.db.repo import Repo
from bot.services import roles
from bot.services.admin_actions import AdminContext, Done, Target, available, perform
from bot.services.roles import Access

CHAT, OTHER = -1001, -1002
MIGRATION = Path("bot/db/migrations/141_chat_admins.sql").read_text(encoding="utf-8")
ADDER, MEMBER, STRANGER = 10, 11, 12


def _settings(*superadmins: int) -> SimpleNamespace:
    return SimpleNamespace(is_superadmin=lambda tg_id: tg_id in superadmins)


async def _chat(repo: Repo, chat_id: int = CHAT) -> None:
    await repo.upsert_chat(chat_id, f"chat {chat_id}", ADDER)


def test_the_table() -> None:
    user = Access()
    chat_admin = Access(chats=frozenset({CHAT}))
    app_admin = Access(role=roles.ADMIN)
    superadmin = Access(role=roles.SUPERADMIN)
    assert not user.any
    assert [a.allows("chat", CHAT) for a in (user, chat_admin, app_admin, superadmin)] == [
        False,
        True,
        True,
        True,
    ]
    assert not chat_admin.allows("chat", OTHER)
    assert [a.allows("admin") for a in (user, chat_admin, app_admin, superadmin)] == [
        False,
        False,
        True,
        True,
    ]
    assert [a.allows("superadmin") for a in (chat_admin, app_admin, superadmin)] == [
        False,
        False,
        True,
    ]


async def test_access_of_reads_the_role_and_the_chats(repo: Repo) -> None:
    await _chat(repo)
    await repo.ensure_user(ADDER, "adder")
    await repo.set_chat_admin(CHAT, ADDER, None)
    access = await roles.access_of(repo, _settings(), ADDER)
    assert access.role == roles.USER and access.chats == {CHAT}
    # The environment's super-admin is one whatever the column says.
    assert (await roles.access_of(repo, _settings(STRANGER), STRANGER)).superadmin


async def test_the_chat_admin_is_one_and_goes_with_the_bot(repo: Repo) -> None:
    await _chat(repo)
    await repo.set_chat_admin(CHAT, ADDER, None)
    await repo.set_chat_admin(CHAT, MEMBER, ADDER)  # handed on: one per chat
    assert await repo.chat_admin(CHAT) == MEMBER
    assert await repo.chats_admined_by(ADDER) == []
    await repo.deactivate_chat(CHAT)
    assert await repo.chat_admin(CHAT) is None


async def test_the_role_goes_to_the_chats_members_only(repo: Repo) -> None:
    await _chat(repo)
    for tg_id, name in ((MEMBER, "member"), (STRANGER, "stranger")):
        await repo.ensure_user(tg_id, name)
    await repo.subscribe(CHAT, await repo.person_id(MEMBER))
    assert [row[0] for row in await repo.chat_admin_candidates(CHAT)] == [MEMBER]


async def test_actions_follow_the_role(repo: Repo) -> None:
    await _chat(repo)
    await _chat(repo, OTHER)
    await repo.ensure_user(MEMBER, "member")
    person = await repo.person_id(MEMBER)

    async def ids(access: Access, scope: str, target: Target) -> set[str]:
        ctx = AdminContext(repo, None, access=access)  # type: ignore[arg-type]
        return {v.id for v in await available(ctx, scope, target, locale="ru")}  # type: ignore[arg-type]

    chat_admin = Access(chats=frozenset({CHAT}))
    assert "delete_last" in await ids(chat_admin, "chat", Target(chat_id=CHAT))
    assert not await ids(chat_admin, "chat", Target(chat_id=OTHER))
    assert not await ids(chat_admin, "user", Target(person=person))
    assert "delete" not in await ids(Access(role=roles.ADMIN), "user", Target(person=person))
    assert "delete" in await ids(Access(role=roles.SUPERADMIN), "user", Target(person=person))

    ctx = AdminContext(repo, None, access=chat_admin)  # type: ignore[arg-type]
    refused = await perform(ctx, "user", Target(person=person), "delete", 2, locale="ru")
    assert isinstance(refused, Done) and not refused.ok
    assert await repo.get_user(person) is not None


async def test_publishing_off_keeps_the_chat_out_of_the_targets(repo: Repo) -> None:
    await _chat(repo)
    await repo.ensure_user(MEMBER, "member")
    person = await repo.person_id(MEMBER)
    await repo.subscribe(CHAT, person)
    assert [t.chat_id for t in await repo.publication_targets(person)] == [CHAT]
    await repo.update_chat_settings(CHAT, publishing=0)
    assert await repo.publication_targets(person) == []


async def test_the_super_admin_gives_app_roles_one_step_at_a_time(repo: Repo) -> None:
    for tg_id, name in ((ADDER, "boss"), (MEMBER, "member"), (STRANGER, "fixed")):
        await repo.ensure_user(tg_id, name)
    member = await repo.person_id(MEMBER)
    settings = _settings(ADDER, STRANGER)
    ctx = AdminContext(repo, settings, access=Access(role=roles.SUPERADMIN), admin_id=ADDER)  # type: ignore[arg-type]

    async def ids(person: int, context: AdminContext = ctx) -> set[str]:
        views = await available(context, "user", Target(person=person), locale="ru")
        return {v.id for v in views} & {
            "make_admin",
            "make_superadmin",
            "unmake_admin",
            "unmake_superadmin",
        }

    assert await ids(member) == {"make_admin"}
    assert await perform(ctx, "user", Target(person=member), "make_admin", 1, locale="ru")
    assert await repo.person_role(member) == roles.ADMIN
    assert await ids(member) == {"make_superadmin", "unmake_admin"}
    # Never oneself, never one the environment names, never by an app admin.
    assert await ids(await repo.person_id(ADDER)) == set()
    assert await ids(await repo.person_id(STRANGER)) == set()
    app_admin = AdminContext(repo, settings, access=Access(role=roles.ADMIN), admin_id=MEMBER)  # type: ignore[arg-type]
    assert await ids(await repo.person_id(ADDER), app_admin) == set()
