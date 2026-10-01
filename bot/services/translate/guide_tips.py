"""Which lines of a Steam guide are an achievement's tip — chosen by Haiku.

Guides are laid out by their authors, each differently, and rules guessing where
one achievement's section ends broke on every new guide (owner, 2026-09-30). Only
a guide that names its achievements on lines of their own is used (owner,
2026-10-01: every other layout came out crooked): it is cut into blocks, one from
each name to the next, and the model picks, inside each block, the lines that help
to get that achievement. It only *points*: it answers with line numbers of the
block, and the tip is those lines copied as they are, so nothing is invented and
pictures, videos, lists and tables survive. No key, a failed call or a malformed
answer: no tips.
"""

from __future__ import annotations

import logging

from bot.services.translate.client import ask_model

log = logging.getLogger(__name__)

# A guide longer than this is not sent at all: it is a wiki, not a guide.
MAX_LINES = 2500
_PROMPT_LINE_CHARS = 240
MAX_SECTION_LINES = 400
_MAX_OUTPUT_TOKENS = 8192
_SEPARATOR = "§"

# A guide naming fewer achievements than this on lines of their own is passed over.
MIN_NAMED = 3


def _parts(line: str) -> list[str]:
    """One answer line split at the separator; a separator left dangling at the
    end (models like to close a line with one) is not a part."""
    return [part.strip() for part in line.strip().removesuffix(_SEPARATOR).split(_SEPARATOR)]


def blocks_of(lines: tuple[str, ...], marks: dict[int, int]) -> list[tuple[int, int, int]]:
    """(achievement number, first line, last line) for each stretch of a guide from an
    achievement's name to the next name. The name line is not part of its block,
    and a name with nothing under it before the next one has no block."""
    starts = sorted(marks)
    blocks = []
    for position, mark in enumerate(starts):
        end = (starts[position + 1] - 1) if position + 1 < len(starts) else len(lines) - 1
        if end > mark:
            blocks.append((marks[mark], mark + 1, end))
    return blocks


def _blocks_prompt(
    lines: tuple[str, ...],
    blocks: list[tuple[int, int, int]],
    achievements: list[tuple[str, str]],
) -> str:
    shown = []
    for number, (achievement, first, last) in enumerate(blocks, start=1):
        name, description = achievements[achievement - 1]
        body = "\n".join(
            f"{i + 1}. {lines[first + i][:_PROMPT_LINE_CHARS]}" for i in range(last - first + 1)
        )
        shown.append(
            f'BLOCK {number}: achievement "{name}"'
            + (f" ({description})" if description else "")
            + f"\n{body}"
        )
    return (
        "Below are blocks cut from a Steam guide for a video game. Each block holds "
        "the lines that follow one achievement's name in the guide, numbered from 1 "
        "within the block (a line that is only an address is a picture, a video or a "
        "link; table rows join their cells with ¦).\n\n"
        "For each block select the lines that help the player get that achievement: "
        "its text, lists, tables, pictures and videos, all of it, however long; never "
        "stop in the middle of a table or a list. Leave out what the achievement's "
        "description already says, and everything the author says to the reader rather "
        "than about the game (greetings, introductions, thanks, credits, requests, "
        "slogans, notes on translation, navigation), and anything that belongs to "
        "another topic or achievement. Where such lines sit inside the useful ones, "
        "give several pieces. If nothing in a block helps, leave the block out.\n\n"
        "If the guide is written in neither English nor Russian, reply with only the "
        "word SKIP.\n\n"
        "Reply with ONLY lines of this form, one per piece, three numbers separated by "
        "the character §: the block number, the first line, the last line. For "
        "example:\n3 § 1 § 9\n3 § 12 § 14\n7 § 2 § 6\nNothing else.\n\n" + "\n\n".join(shown)
    )


def parse_blocks(
    reply: str, blocks: list[tuple[int, int, int]]
) -> dict[int, list[tuple[int, int]]]:
    """The model's answer about blocks as {achievement number: [(first, last), ...]}
    in 0-based inclusive lines of the whole guide. Anything malformed or outside its
    block is dropped."""
    sections: dict[int, list[tuple[int, int]]] = {}
    for line in reply.splitlines():
        parts = _parts(line)
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            continue
        number, first, last = (int(part) for part in parts)
        if not (1 <= number <= len(blocks)):
            continue
        achievement, start, end = blocks[number - 1]
        if not (1 <= first <= last <= end - start + 1):
            continue
        ranges = sections.setdefault(achievement, [])
        piece = (start + first - 1, start + last - 1)
        if ranges and piece[0] <= ranges[-1][1]:
            continue
        if sum(b - a + 1 for a, b in ranges) + (piece[1] - piece[0] + 1) > MAX_SECTION_LINES:
            continue
        ranges.append(piece)
    return sections


async def _ask(api_key: str, prompt: str) -> str | None:
    """One question to the model; None when it could not be asked or answered."""
    return await ask_model(api_key, prompt, max_tokens=_MAX_OUTPUT_TOKENS, what="guide-tips")


async def locate_sections(
    api_key: str,
    lines: tuple[str, ...],
    achievements: list[tuple[str, str]],
    marks: dict[int, int] | None = None,
) -> dict[int, list[tuple[int, int]]] | None:
    """For each achievement (name, description) the guide covers: the pieces
    (first and last line, 0-based inclusive) that are about it. `marks` says which
    lines are exactly an achievement's name ({line index: achievement number, from
    1}); a guide with fewer than MIN_NAMED of them is passed over (an empty dict).
    None when the model could not be asked."""
    marks = marks or {}
    if not lines or not achievements or len(lines) > MAX_LINES or len(marks) < MIN_NAMED:
        return {}
    blocks = blocks_of(lines, marks)
    if not blocks:
        return {}
    reply = await _ask(api_key, _blocks_prompt(lines, blocks, achievements))
    if reply is None:
        return None
    if reply.strip().upper().startswith("SKIP"):
        log.info("anthropic guide-tips: a guide in another language, passed over")
        return {}
    found = parse_blocks(reply, blocks)
    sections = {achievement - 1: ranges for achievement, ranges in found.items()}
    log.info(
        "anthropic guide-tips: %s achievements located in a guide of %s lines (%s blocks)",
        len(sections),
        len(lines),
        len(blocks),
    )
    if not sections and reply.strip():
        log.info("anthropic guide-tips: nothing usable in the answer: %r", reply[:200])
    return sections
