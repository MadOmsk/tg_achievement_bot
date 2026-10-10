"""Every action the super-admin takes on a person, a game account or a chat,
described once (#176; owner, 2026-10-08: actions work like the settings — a
new one appears in the bot and the Mini App at once).

An action says what it is about (`user`, `account`, `chat`), its label,
whether it is dangerous, how many times it is confirmed and with what words,
and what it does. Both panels list the actions of a card from here
(`available`) and take one a step at a time (`perform`): every step but the
last answers `Confirm` — the words to show and the label of the "yes" —, the
last one runs it and answers `Done`. The bot draws a confirmation as a screen
with "yes" / "cancel", the Mini App as a dialog; the steps, the words and the
checks are the same.

A new action is one class here and its `admin.ftl` strings. A new way to
confirm or a new kind of input is added once, for both panels.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from bot.config import Settings
from bot.constants import Platform
from bot.db.repo import ChatTarget, PlatformLink, Repo, User
from bot.i18n import gettext
from bot.services import admin_cleanup, custom_avatars
from bot.services.admin_accounts import AdminAccounts
from bot.services.admin_cleanup import WIPE_WINDOW_HOURS, Wipe
from bot.services.admin_settings import TOAST_PREVIEW_MAX_CHARS
from bot.services.naming import link_nickname, person_name_of

log = logging.getLogger(__name__)

Scope = Literal["user", "account", "chat"]

# Plain platform names for a sentence ("Стереть базу PSN: nick …").
_PLATFORM_NAMES = {"xbox": "XBOX", "steam": "Steam", "psn": "PSN"}


@dataclass(frozen=True, slots=True)
class Target:
    """What an action is about, and how both panels name it in a button or a
    request: `p12` a person, `p12.psn.<account id>` one of their accounts,
    `-100…` a chat."""

    person: int | None = None
    platform: str | None = None
    account: str | None = None
    chat_id: int | None = None

    def encode(self) -> str:
        if self.chat_id is not None:
            return str(self.chat_id)
        base = f"p{self.person}"
        if self.platform is None:
            return base
        return f"{base}.{self.platform}" + (f".{self.account}" if self.account else "")

    @classmethod
    def decode(cls, scope: Scope, raw: str) -> Target:
        """Raises ValueError for anything that is not a target of `scope`."""
        if scope == "chat":
            return cls(chat_id=int(raw))
        if not raw.startswith("p"):
            raise ValueError(raw)
        person, _, rest = raw[1:].partition(".")
        if scope == "user":
            if rest:
                raise ValueError(raw)
            return cls(person=int(person))
        platform, _, account = rest.partition(".")
        if platform not in ("xbox", "steam", "psn"):
            raise ValueError(raw)
        return cls(person=int(person), platform=platform, account=account or None)


@dataclass(slots=True)
class AdminContext:
    """What an action may need — every caller builds one from what it holds."""

    repo: Repo
    settings: Settings
    bot: Any = None
    xbox: Any = None
    steam: Any = None
    psn: Any = None
    admin_id: int | None = None
    # Posting the app's promo to a chat — the caller's (it is Telegram's).
    send_promo: Callable[[ChatTarget], Awaitable[None]] | None = None
    # A person's latest posts in every picture style, to the super-admin's
    # own DM — the caller's too; answers how many pictures went.
    send_picture_samples: Callable[[int], Awaitable[int]] | None = None

    def accounts(self) -> AdminAccounts:
        return AdminAccounts(
            self.repo, self.settings, xbox=self.xbox, steam=self.steam, psn=self.psn
        )


@dataclass(frozen=True, slots=True)
class ActionView:
    """One action as a card shows it."""

    id: str
    scope: Scope
    target: str
    label: str
    danger: bool
    # Where the bot puts it: a chat's root card or its «Сообщения»; `row`
    # puts an account's actions side by side.
    section: str | None
    row: str


@dataclass(frozen=True, slots=True)
class Confirm:
    text: str
    yes: str
    step: int  # the step that the "yes" asks for


@dataclass(frozen=True, slots=True)
class Done:
    ok: bool
    text: str | None = None
    # `toast` — a short line; `card` — longer, shown under the card (a
    # refresh's report); the person is gone, back to the list (`gone`).
    show: Literal["toast", "card"] = "toast"
    gone: bool = False


# ------------------------------------------------------------------ actions


@dataclass
class _Subject:
    """What one action needs to know about its target, read once."""

    user: User | None = None
    link: PlatformLink | None = None
    chat: ChatTarget | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class _Action:
    id: ClassVar[str]
    scope: ClassVar[Scope]
    danger: ClassVar[bool] = False
    confirms: ClassVar[int] = 0
    section: ClassVar[str | None] = None
    order: ClassVar[int] = 50

    async def available(self, ctx: AdminContext, target: Target, subject: _Subject) -> bool:
        return True

    def label(self, subject: _Subject, target: Target, _: Callable[..., str]) -> str:
        raise NotImplementedError

    async def precheck(
        self, ctx: AdminContext, target: Target, subject: _Subject, _: Callable[..., str]
    ) -> Done | None:
        """A reason not to ask at all (nothing to wipe, say)."""
        return None

    def confirm(
        self, step: int, subject: _Subject, target: Target, _: Callable[..., str]
    ) -> tuple[str, str]:
        raise NotImplementedError

    async def run(self, ctx: AdminContext, target: Target, subject: _Subject, locale: str) -> Done:
        raise NotImplementedError


class _Exclude(_Action):
    id, scope, order = "exclude", "user", 10

    def label(self, subject, target, _):
        return (
            _("admin-restore") if subject.user and subject.user.is_excluded else _("admin-exclude")
        )

    async def run(self, ctx, target, subject, locale):
        excluded = not (subject.user and subject.user.is_excluded)
        await ctx.repo.set_excluded(target.person, excluded, ctx.admin_id)  # type: ignore[arg-type]
        _ = _translator(locale)
        return Done(True, _("admin-user-excluded") if excluded else _("admin-user-restored"))


class _Sync(_Action):
    id, scope, order = "sync", "account", 20

    def label(self, subject, target, _):
        return _account_label(subject, target, _, "refresh")

    async def run(self, ctx, target, subject, locale):
        _ = _translator(locale)
        try:
            summary = await ctx.accounts().refresh(
                target.platform,
                target.person,
                locale=locale,
                account_id=target.account,  # type: ignore[arg-type]
            )
        except Exception:
            log.exception("admin refresh of %s failed", target.encode())
            return Done(False, _("admin-refresh-failed"))
        if summary is None:
            return Done(False, _("admin-user-not-connected"))
        return Done(True, summary, show="card")


class _Reset(_Action):
    id, scope, danger, confirms, order = "reset", "account", True, 1, 21

    def label(self, subject, target, _):
        return _account_label(subject, target, _, "reset")

    def confirm(self, step, subject, target, _):
        name = _PLATFORM_NAMES[target.platform or ""]
        if subject.link is not None and target.account:
            name = f"{name}: {link_nickname(subject.link)}"
        return _("admin-reset-confirm-prompt", platform=name), _("admin-reset-confirm-yes")

    async def run(self, ctx, target, subject, locale):
        _ = _translator(locale)
        try:
            done = await ctx.accounts().reset(target.platform, target.person, target.account)  # type: ignore[arg-type]
        except Exception:
            log.exception("admin reset of %s failed", target.encode())
            return Done(False, _("admin-refresh-failed"))
        return (
            Done(True, _("admin-refreshing"))
            if done
            else Done(False, _("admin-user-not-connected"))
        )


class _AvatarReset(_Action):
    id, scope, order = "avatar_reset", "user", 30

    async def available(self, ctx, target, subject):
        return bool(await ctx.repo.custom_avatar_path(target.person))  # type: ignore[arg-type]

    def label(self, subject, target, _):
        return _("admin-reset-avatar")

    async def run(self, ctx, target, subject, locale):
        await custom_avatars.clear(ctx.repo, target.person)  # type: ignore[arg-type]
        return Done(True, _translator(locale)("admin-avatar-reset"))


class _PictureTest(_Action):
    """The person's latest achievement on each platform, as a post in every
    picture style, sent to the super-admin's DM (owner, 2026-10-10): the
    styles are compared on real posts before one is switched on."""

    id, scope, order = "picture_test", "user", 35

    def label(self, subject, target, _):
        return _("admin-picture-test")

    async def run(self, ctx, target, subject, locale):
        _ = _translator(locale)
        if ctx.send_picture_samples is None:
            return Done(False, _("admin-picture-test-failed"))
        try:
            sent = await ctx.send_picture_samples(target.person)  # type: ignore[arg-type]
        except Exception:
            log.exception("picture samples for %s failed", target.encode())
            return Done(False, _("admin-picture-test-failed"))
        if not sent:
            return Done(False, _("admin-picture-test-empty"))
        return Done(True, _("admin-picture-test-sent", count=sent))


class _Delete(_Action):
    id, scope, danger, confirms, order = "delete", "user", True, 2, 90

    def label(self, subject, target, _):
        return _("admin-delete-user")

    def confirm(self, step, subject, target, _):
        assert subject.user is not None
        fields = {
            "name": person_name_of(subject.user),
            "tg_id": str(subject.user.tg_id) if subject.user.tg_id else "—",
        }
        if step == 1:
            return _("admin-delete-confirm-1", **fields), _("admin-delete-confirm-1-yes")
        return _("admin-delete-confirm-2", **fields), _("admin-delete-confirm-2-yes")

    async def run(self, ctx, target, subject, locale):
        _ = _translator(locale)
        deleted = await ctx.repo.delete_person(target.person, is_superadmin=True)  # type: ignore[arg-type]
        if not deleted:
            return Done(False, _("admin-delete-not-found"))
        return Done(True, _("admin-delete-toast"), gone=True)


class _Promo(_Action):
    id, scope, confirms, order = "promo", "chat", 1, 10

    def label(self, subject, target, _):
        return _("admin-send-promo-to-chat")

    def confirm(self, step, subject, target, _):
        assert subject.chat is not None
        return (
            _("admin-promo-confirm", title=subject.chat.title or subject.chat.chat_id),
            _("admin-promo-confirm-yes"),
        )

    async def run(self, ctx, target, subject, locale):
        _ = _translator(locale)
        assert subject.chat is not None
        if ctx.send_promo is None:
            return Done(False, _("admin-promo-failed"))
        try:
            await ctx.send_promo(subject.chat)
        except Exception as exc:
            log.info("promo to chat %s failed: %r", target.chat_id, exc)
            return Done(False, _("admin-promo-failed"))
        return Done(True, _("admin-promo-sent"))


class _DeleteLast(_Action):
    id, scope, section, order = "delete_last", "chat", "messages", 20

    def label(self, subject, target, _):
        return _("admin-delete-last")

    async def run(self, ctx, target, subject, locale):
        _ = _translator(locale)
        result = await admin_cleanup.delete_last(ctx.bot, ctx.repo, target.chat_id)  # type: ignore[arg-type]
        if result is None:
            return Done(False, _("admin-no-bot-messages"))
        if not result.deleted:
            return Done(False, _("admin-delete-old-failed"))
        if result.preview:
            return Done(
                True, _("admin-deleted-last-preview", preview=toast_preview(result.preview))
            )
        return Done(True, _("admin-deleted-last"))


class _Wipe(_Action):
    scope, danger, confirms, section = "chat", True, 1, "messages"
    kind: ClassVar[Wipe]
    label_key: ClassVar[str]
    prompt_key: ClassVar[str]
    empty_key: ClassVar[str]

    def label(self, subject, target, _):
        return _(self.label_key)

    async def precheck(self, ctx, target, subject, _):
        ids = await admin_cleanup.messages_to_wipe(ctx.repo, target.chat_id, self.kind)  # type: ignore[arg-type]
        subject.extra["count"] = len(ids)
        return None if ids else Done(False, _(self.empty_key))

    def confirm(self, step, subject, target, _):
        assert subject.chat is not None
        title = subject.chat.title or subject.chat.chat_id
        return (
            _(
                self.prompt_key,
                count=subject.extra.get("count", 0),
                title=title,
                hours=WIPE_WINDOW_HOURS,
            ),
            _("admin-confirm-delete"),
        )

    async def run(self, ctx, target, subject, locale):
        _ = _translator(locale)
        ids = await admin_cleanup.messages_to_wipe(ctx.repo, target.chat_id, self.kind)  # type: ignore[arg-type]
        ok = await admin_cleanup.wipe(ctx.bot, ctx.repo, target.chat_id, ids)  # type: ignore[arg-type]
        return Done(ok, _("admin-wipe-done") if ok else _("admin-wipe-partial"))


class _Wipe24h(_Wipe):
    id, kind, order = Wipe.ALL_24H.value, Wipe.ALL_24H, 30
    label_key, prompt_key, empty_key = (
        "admin-wipe-bot-24h",
        "admin-wipe-prompt",
        "admin-no-bot-messages-24h",
    )


class _WipeSystem24h(_Wipe):
    id, kind, order = Wipe.SYSTEM_24H.value, Wipe.SYSTEM_24H, 31
    label_key, prompt_key, empty_key = (
        "admin-wipe-system-24h",
        "admin-system-wipe-prompt",
        "admin-no-system-messages",
    )


class _WipeSystemAll(_Wipe):
    id, kind, order = Wipe.SYSTEM_ALL.value, Wipe.SYSTEM_ALL, 32
    label_key, prompt_key, empty_key = (
        "admin-wipe-system-all",
        "admin-system-wipe-prompt",
        "admin-no-system-messages",
    )


ACTIONS: tuple[_Action, ...] = (
    _Exclude(),
    _Sync(),
    _Reset(),
    _AvatarReset(),
    _PictureTest(),
    _Delete(),
    _Promo(),
    _DeleteLast(),
    _Wipe24h(),
    _WipeSystem24h(),
    _WipeSystemAll(),
)
_BY_ID: dict[tuple[str, str], _Action] = {(a.scope, a.id): a for a in ACTIONS}


# ------------------------------------------------------------------ the API


async def available(
    ctx: AdminContext, scope: Literal["user", "chat"], target: Target, *, locale: str
) -> list[ActionView]:
    """A card's actions: a person's own and their accounts', or a chat's."""
    _ = _translator(locale)
    targets: list[tuple[Scope, Target]] = [(scope, target)]
    if scope == "user":
        targets += [("account", t) for t in await _accounts_of(ctx.repo, target.person)]  # type: ignore[arg-type]
    views: list[tuple[int, int, ActionView]] = []
    for index, (action_scope, action_target) in enumerate(targets):
        subject = await _subject(ctx, action_scope, action_target)
        if subject is None:
            continue
        for action in ACTIONS:
            if action.scope != action_scope:
                continue
            if not await action.available(ctx, action_target, subject):
                continue
            encoded = action_target.encode()
            views.append(
                (
                    action.order // 10,
                    index,
                    ActionView(
                        id=action.id,
                        scope=action.scope,
                        target=encoded,
                        label=action.label(subject, action_target, _),
                        danger=action.danger,
                        section=action.section,
                        row=encoded if action_scope == "account" else f"{encoded}:{action.id}",
                    ),
                )
            )
    return [view for _o, _i, view in sorted(views, key=lambda item: (item[0], item[1]))]


async def perform(
    ctx: AdminContext, scope: Scope, target: Target, action_id: str, step: int, *, locale: str
) -> Confirm | Done:
    """Step `step` of an action: 0 is the tap. Answers the next confirmation,
    or — once every one was given — what running it did."""
    _ = _translator(locale)
    action = _BY_ID.get((scope, action_id))
    if action is None:
        return Done(False, _("admin-action-unknown"))
    subject = await _subject(ctx, scope, target)
    if subject is None or not await action.available(ctx, target, subject):
        return Done(False, _("admin-action-unknown"))
    if step == 0:
        early = await action.precheck(ctx, target, subject, _)
        if early is not None:
            return early
    if step < action.confirms:
        if step > 0:
            await action.precheck(ctx, target, subject, _)
        text, yes = action.confirm(step + 1, subject, target, _)
        return Confirm(text, yes, step + 1)
    return await action.run(ctx, target, subject, locale)


# ------------------------------------------------------------------ helpers


def _translator(locale: str) -> Callable[..., str]:
    def _(key: str, **kwargs: Any) -> str:
        return gettext("admin", key, locale=locale, **kwargs)

    return _


def toast_preview(text: str) -> str:
    """A deleted message's first lines for a toast: one line, and short
    enough to leave room for the words around it (Telegram caps a callback
    answer at 200 characters; `bot_messages.preview` can be 200 itself)."""
    collapsed = " ".join(text.splitlines())
    if len(collapsed) <= TOAST_PREVIEW_MAX_CHARS:
        return collapsed
    return collapsed[: TOAST_PREVIEW_MAX_CHARS - 1] + "…"


def _account_label(
    subject: _Subject, target: Target, _: Callable[..., str], verb: Literal["refresh", "reset"]
) -> str:
    if target.platform == "psn" and target.account and subject.extra.get("several"):
        return _(f"admin-{verb}-psn-account", name=link_nickname(subject.link))  # type: ignore[arg-type]
    return _(f"admin-{verb}-{target.platform}")


async def _accounts_of(repo: Repo, person: int) -> list[Target]:
    """The person's game accounts in the display order: Xbox, each PSN, Steam."""
    user = await repo.get_user(person)
    found: list[Target] = []
    if user is not None and user.xuid:
        found.append(Target(person=person, platform="xbox"))
    for link in await repo.platform_links_for(person, Platform.PSN):
        found.append(Target(person=person, platform="psn", account=link.external_id))
    if await repo.get_platform_link(person, Platform.STEAM) is not None:
        found.append(Target(person=person, platform="steam"))
    return found


async def _subject(ctx: AdminContext, scope: Scope, target: Target) -> _Subject | None:
    repo = ctx.repo
    if scope == "chat":
        chat = next((c for c in await repo.admin_chats() if c.chat_id == target.chat_id), None)
        return None if chat is None else _Subject(chat=chat)
    user = await repo.get_user(target.person) if target.person is not None else None  # type: ignore[arg-type]
    if user is None:
        return None
    if scope == "user":
        return _Subject(user=user)
    if target.platform == "xbox":
        return _Subject(user=user) if user.xuid else None
    platform = Platform.PSN if target.platform == "psn" else Platform.STEAM
    links = await repo.platform_links_for(target.person, platform)  # type: ignore[arg-type]
    link = next(
        (lnk for lnk in links if target.account is None or lnk.external_id == target.account),
        None,
    )
    if link is None:
        return None
    return _Subject(user=user, link=link, extra={"several": len(links) > 1})
