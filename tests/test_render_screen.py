"""Every screen `scripts/render_screen.py` knows how to draw must still draw.

That script is the project's own way of looking at a screen (#63), which
makes it the one place every view is called from a single list — and it is
outside the test suite, so a view whose signature changed under it fails
only when somebody runs it by hand. That is how `build_stats_text` gaining a
`chat_id` went out to the test bot with the script still passing an
`I18nContext` in its place (2026-09-17), and it is the same class of fault
as the admin buttons that were dead on arrival because a test asserted the
keyboard was *drawn* and never invoked the handler.

The assertion is deliberately weak — it builds, it does not raise — because
what each screen *says* is covered by that screen's own tests. What is not
covered anywhere else is that the call still type-checks at runtime.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from bot.db.repo import Repo
from bot.views import Screen


def _load_render_screen():
    """Loaded by path, not by name: `scripts/` is a directory of one-off
    entry points, not an installed package, so `import scripts.render_screen`
    only works from a shell sitting in the repository root. Registered in
    `sys.modules` before it is executed because its dataclasses resolve their
    own annotations at class-creation time."""
    path = Path(__file__).resolve().parent.parent / "scripts" / "render_screen.py"
    spec = importlib.util.spec_from_file_location("render_screen", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render_screen = _load_render_screen()

# The two that need a Settings (a Fernet key, the platform keys) rather than
# just a repo. They build their own auth wrappers, which read the database
# lazily — but constructing a real Settings here would mean a fixture whose
# only purpose is to satisfy a script.
NEEDS_SETTINGS = {"admin-home", "admin-keys"}

TG_ID = 4242
CHAT_ID = -100500


@pytest.fixture
async def context(repo: Repo):
    await repo.ensure_user(TG_ID, "someone", "Some", "One")
    await repo.link_xbox_account(TG_ID, "xuid-render", "SomeGamertag", 1000)
    await repo.upsert_chat(CHAT_ID, "A Chat", TG_ID)
    await repo.subscribe(CHAT_ID, TG_ID)
    return render_screen.Context(
        repo=repo,
        settings=None,  # type: ignore[arg-type]
        tg_id=TG_ID,
        chat_id=CHAT_ID,
        locale="ru",
    )


@pytest.mark.parametrize(
    "name", sorted(name for name in render_screen.SCREENS if name not in NEEDS_SETTINGS)
)
async def test_every_screen_still_builds(name: str, context) -> None:
    built = await render_screen.SCREENS[name](context)
    assert built is None or isinstance(built, Screen)


def test_the_screens_needing_settings_are_still_the_ones_we_think() -> None:
    """If one of those two loses its Settings dependency, it should join the
    parametrized sweep above rather than sit in an exception list forever."""
    assert NEEDS_SETTINGS <= set(render_screen.SCREENS)
