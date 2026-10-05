"""Every shipped locale must stay structurally identical (#48).

Translations drift: someone adds a key to ru and forgets en, or renames a
variable on one side only. Neither shows up until the screen is actually
rendered in that language — and with per-key fallback (LOCALES_MAP) a
missing key degrades silently to Russian rather than failing loudly, which
is right in production and useless as a warning. These tests are that
warning.

They deliberately assert *structure*, never wording: what the English text
says is a translation decision, that it has the same keys carrying the same
variables is a correctness one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from aiogram_i18n.cores.fluent_runtime_core import FluentRuntimeCore

from bot.i18n import AVAILABLE_LOCALES, DEFAULT_LOCALE, LOCALES_DIR

KEY_RE = re.compile(r"^([a-zA-Z][\w-]*)\s*=", re.M)
VAR_RE = re.compile(r"\$([a-zA-Z][\w-]*)")

SECONDARY_LOCALES = [locale for locale in AVAILABLE_LOCALES if locale != DEFAULT_LOCALE]


def _messages_dir(locale: str) -> Path:
    return LOCALES_DIR / locale / "LC_MESSAGES"


def _entries(path: Path) -> dict[str, set[str]]:
    """key -> the set of $variables its value references. Comment lines are
    stripped first: several of them mention a variable in prose, and a
    comment is not part of the message."""
    text = "\n".join(
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    matches = list(KEY_RE.finditer(text))
    entries: dict[str, set[str]] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        entries[match.group(1)] = set(VAR_RE.findall(text[match.end() : end]))
    return entries


@pytest.mark.parametrize("locale", SECONDARY_LOCALES)
def test_locale_has_the_same_files(locale: str) -> None:
    reference = {path.name for path in _messages_dir(DEFAULT_LOCALE).glob("*.ftl")}
    translated = {path.name for path in _messages_dir(locale).glob("*.ftl")}
    assert translated == reference


@pytest.mark.parametrize("locale", SECONDARY_LOCALES)
def test_locale_has_the_same_keys_and_variables(locale: str) -> None:
    missing_keys: list[str] = []
    extra_keys: list[str] = []
    bad_variables: list[str] = []

    for path in sorted(_messages_dir(DEFAULT_LOCALE).glob("*.ftl")):
        reference = _entries(path)
        translated = _entries(_messages_dir(locale) / path.name)
        missing_keys += [f"{path.name}:{key}" for key in sorted(set(reference) - set(translated))]
        extra_keys += [f"{path.name}:{key}" for key in sorted(set(translated) - set(reference))]
        for key in sorted(set(reference) & set(translated)):
            if reference[key] != translated[key]:
                bad_variables.append(
                    f"{path.name}:{key} ru={sorted(reference[key])} "
                    f"{locale}={sorted(translated[key])}"
                )

    assert missing_keys == []
    assert extra_keys == []
    assert bad_variables == []


async def test_every_key_renders_in_every_locale() -> None:
    """Parse and format every message in every locale, so a Fluent syntax
    error or a selector with no matching variant fails here rather than on
    the one screen that happens to use it."""
    core = FluentRuntimeCore(path=LOCALES_DIR / "{locale}" / "LC_MESSAGES")
    await core.startup()

    assert set(core.available_locales) == set(AVAILABLE_LOCALES)

    failures: list[str] = []
    for path in sorted(_messages_dir(DEFAULT_LOCALE).glob("*.ftl")):
        for key, variables in _entries(path).items():
            # 1 for everything: it interpolates fine, and it is also a real
            # number for the plural selectors, which a string would silently
            # send to the default variant instead of exercising.
            arguments = dict.fromkeys(variables, 1)
            for locale in AVAILABLE_LOCALES:
                try:
                    core.get(key, locale, **arguments)
                except Exception as error:  # collected and reported, not raised
                    failures.append(f"{locale}/{path.name}:{key}: {error!r}")

    assert failures == []
