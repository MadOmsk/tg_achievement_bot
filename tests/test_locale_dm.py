"""DM-shaped messages render in their recipient's language (#48).

Everything here is sent outside an aiogram update — a scheduled reminder, an
admin notification, a post-login DM — so none of it gets an I18nContext and
all of it had to learn to look the locale up for itself. The recipient is
always exactly one known person, which is what makes that possible.
"""

from __future__ import annotations

from bot.db.repo import Repo
from bot.poller.reminders import ReminderJob, keyboard
from bot.services.notify import AdminNotifier

ADMIN_ID = 500
USER_ID = 501


class _FakeBot:
    """Records (chat_id, text) instead of talking to Telegram."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, **_kwargs: object) -> None:
        self.sent.append((chat_id, text))


def test_reminder_keyboard_follows_the_recipients_language() -> None:
    russian = keyboard("ru")
    english = keyboard("en")
    assert russian.inline_keyboard[0][0].text == "🔄 Подключить заново"
    assert english.inline_keyboard[0][0].text == "🔄 Connect again"


async def test_a_reminder_is_sent_in_the_persons_own_language(repo: Repo, cipher) -> None:
    await repo.ensure_user(USER_ID)
    await repo.update_user_settings(USER_ID, locale="en")
    await repo.save_refresh_token(USER_ID, cipher.encrypt("refresh"))
    await repo.set_token_status(USER_ID, "invalid")

    bot = _FakeBot()
    await ReminderJob(bot, repo).run()  # type: ignore[arg-type]

    assert bot.sent, "the reminder never went out"
    _chat_id, text = bot.sent[0]
    assert "Your Xbox access has expired" in text


async def test_the_same_reminder_stays_russian_by_default(repo: Repo, cipher) -> None:
    await repo.ensure_user(USER_ID)
    await repo.save_refresh_token(USER_ID, cipher.encrypt("refresh"))
    await repo.set_token_status(USER_ID, "invalid")

    bot = _FakeBot()
    await ReminderJob(bot, repo).run()  # type: ignore[arg-type]

    assert bot.sent
    assert "Доступ к Xbox истёк" in bot.sent[0][1]


async def test_admin_notifications_follow_the_admins_own_language(repo: Repo) -> None:
    await repo.ensure_user(ADMIN_ID)
    await repo.update_user_settings(ADMIN_ID, locale="en")
    await repo.ensure_user(USER_ID, username="igor")

    bot = _FakeBot()
    await AdminNotifier(bot, repo, [ADMIN_ID]).user_connected(  # type: ignore[arg-type]
        USER_ID, "MadOmsk", is_new=True
    )

    assert bot.sent == [(ADMIN_ID, "➕ User added: MadOmsk\ntg_id 501 · @igor")]


async def test_two_admins_each_get_their_own_language(repo: Repo) -> None:
    """The reason a notification is built per recipient rather than once:
    admins need not share a locale."""
    second_admin = ADMIN_ID + 1
    await repo.ensure_user(ADMIN_ID)
    await repo.ensure_user(second_admin)
    await repo.ensure_user(USER_ID, username="igor")
    await repo.update_user_settings(ADMIN_ID, locale="en")
    await repo.update_user_settings(second_admin, locale="ru")

    bot = _FakeBot()
    notifier = AdminNotifier(bot, repo, [ADMIN_ID, second_admin])  # type: ignore[arg-type]
    await notifier.translation_key_dead()

    texts = dict(bot.sent)
    assert texts[ADMIN_ID].startswith("⚠️ The Anthropic key is dead")
    assert texts[second_admin].startswith("⚠️ Умер ключ Anthropic")
