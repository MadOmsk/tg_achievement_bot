"""Every game's description translated into Russian at once (owner,
2026-10-30; #230): what the game page would translate on its first visit in
Russian, done for the whole catalog in one run — the same choice of text
(`game_page.to_translate`), the same call and the same storage, so the page
and this script never translate one text twice.

Safe beside a running bot: each translation is one short write to the catalog.
`--dry-run` only counts. The key is the bot's own (`app_settings`, the admin's
«Ключи»), read with the environment's FERNET_KEY.

Usage (the test server: BOT_ENV_FILE=.env.test …):
    .venv/bin/python -m scripts.translate_game_descriptions --dry-run
    .venv/bin/python -m scripts.translate_game_descriptions [--limit 20] [--workers 4]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.services.crypto import TokenCipher
from bot.services.game_page import text_hash, to_translate
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.client import translate_game_description

log = logging.getLogger(__name__)


async def targets(repo: Repo) -> list[tuple[str, int, str]]:
    """The English text each game still shows a Russian reader, each once
    (two games sharing an HLTB entry ask for it once)."""
    found: dict[tuple[str, int], str] = {}
    ids = await repo.game_ids_for_sweep("all")
    for n, game_id in enumerate(ids, 1):
        hltb = await repo.game_hltb(game_id)
        target = to_translate(
            await repo.game_page_versions(game_id), hltb["entry"] if hltb else None
        )
        if target is not None:
            found.setdefault(target[:2], target[2])
        if n % 500 == 0:
            print(f"  looked at {n}/{len(ids)} games, {len(found)} to translate")
    return [(kind, key, english) for (kind, key), english in found.items()]


async def run(schema: str | None, limit: int | None, workers: int, dry_run: bool) -> None:
    settings = get_settings()
    database = await tools.open_database(schema=schema)
    try:
        repo = Repo(database)
        todo = await targets(repo)
        chars = sum(len(english) for _, _, english in todo)
        print(f"{len(todo)} descriptions to translate, {chars} characters of English")
        if dry_run or not todo:
            return
        env_key = (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        )
        cipher = TokenCipher(settings.fernet_key.get_secret_value())
        api_key = await AnthropicAuth(repo, cipher, env_key=env_key).require_key()
        todo = todo[:limit] if limit else todo
        gate = asyncio.Semaphore(workers)
        done = failed = 0
        started = time.monotonic()

        async def one(kind: str, key: int, english: str) -> None:
            nonlocal done, failed
            async with gate:
                translated = await translate_game_description(
                    api_key, english, target_language="ru"
                )
            if not translated:
                failed += 1
                return
            if kind == "version":
                await repo.set_version_description_ru(key, translated, text_hash(english))
            else:
                await repo.set_hltb_summary_ru(key, translated, text_hash(english))
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(todo)} translated ({time.monotonic() - started:.0f} s)")

        await asyncio.gather(*(one(*target) for target in todo))
        print(f"translated {done}, failed {failed} (a failed one is tried again on its page)")
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    tools.add_arguments(parser)
    parser.add_argument("--dry-run", action="store_true", help="count only")
    parser.add_argument("--limit", type=int, help="translate at most this many")
    parser.add_argument("--workers", type=int, default=4, help="calls at once (default 4)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    tools.run(run(args.schema, args.limit, args.workers, args.dry_run))


if __name__ == "__main__":
    main()
