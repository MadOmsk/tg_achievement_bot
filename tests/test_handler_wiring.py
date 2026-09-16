"""Two whole-router checks that used to need a running build (#63).

`scripts/ui_capture/` existed to catch handlers that were dead on arrival —
it found three at once on 2026-09-13, each raising `TypeError: 'str' object
is not callable` the moment somebody pressed the button, because `_` was
bound to the translator and then reused as a throwaway in an unpacking two
lines later. Tests asserted the buttons were *drawn*, which they were.

The capture harness is gone with the mockups it fed. These two tests are
what is left of its value, and they cost a few milliseconds instead of a
whole dispatcher: every handler is checked for that exact shadowing, and
every handler's arguments are checked against what the dispatcher actually
has to inject. Both failures are invisible until a button is pressed in
production.
"""

from __future__ import annotations

import ast
from pathlib import Path

HANDLERS = Path(__file__).resolve().parents[1] / "bot" / "handlers"

# What main.py puts into the dispatcher, plus what aiogram itself injects.
# A handler asking for anything else is one that raises at press time.
INJECTABLE = {
    # main.py's own workflow data
    "repo",
    "connect",
    "fetcher",
    "steam_fetcher",
    "settings",
    "notifier",
    "psn_auth",
    "psn_fetcher",
    "steam_auth",
    "anthropic_auth",
    # aiogram's own
    "bot",
    "bots",
    "event",
    "message",
    "callback",
    "callback_query",
    "query",
    "event_chat",
    "event_from_user",
    "state",
    "i18n",
    "command",
    "dispatcher",
    "data",
    "raw_state",
}


def _handlers() -> list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    found = []
    for path in sorted(HANDLERS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if any("router." in ast.unparse(d) for d in node.decorator_list):
                found.append((f"{path.name}::{node.name}", node))
    return found


def test_every_handler_only_asks_for_what_the_dispatcher_has() -> None:
    """aiogram resolves a handler's arguments by *name*. One typo, or one
    dependency nobody wired into the dispatcher, and the handler raises the
    moment its button is pressed — never at import, never in a test that
    only builds the keyboard."""
    unknown = [
        f"{where}({arg.arg})"
        for where, node in _handlers()
        for arg in node.args.args
        if arg.arg not in INJECTABLE
    ]

    assert not unknown, f"handlers asking for something nobody injects: {unknown}"


def test_no_handler_shadows_its_own_translator() -> None:
    """The 2026-09-13 bug, three times over: `_ = translator("admin",
    locale)` at the top, then `_, _, chat_id = callback.data.split(":")`
    below, and every later `_("some-key")` is a string being called."""
    offenders = []
    for where, node in _handlers():
        binds_translator = False
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign):
                continue
            targets = ast.unparse(ast.Tuple(elts=child.targets, ctx=ast.Load()))
            value = ast.unparse(child.value)
            if targets.startswith("_") and ("translator(" in value or "i18n.get" == value):
                binds_translator = True
                continue
            if binds_translator and any(
                isinstance(t, ast.Tuple) and any(ast.unparse(e) == "_" for e in t.elts)
                for t in child.targets
            ):
                offenders.append(where)
    assert not offenders, f"`_` reused after being bound to a translator in: {offenders}"


def test_the_handlers_package_holds_no_layout() -> None:
    """The line #63 drew: handlers route and act, views render. A keyboard
    built inside a handler is how the old 2172-line admin.py happened."""
    building = [
        path.name
        for path in sorted(HANDLERS.glob("*.py"))
        if "InlineKeyboardBuilder(" in path.read_text(encoding="utf-8")
    ]

    assert not building, f"keyboards are built in bot/views/, not in: {building}"
