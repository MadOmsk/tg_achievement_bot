"""One-time backfill: fetch (and translate) the description of every game
already in `hltb_cache` from before descriptions existed (#2).

`resolve()` fills a description in for a game the *first time somebody looks
it up*, and its own top-up covers a row that has the English side but not the
Russian one. Neither ever re-fetches HLTB's page for a row cached before
migration 035, since there is no way to tell "HLTB has no summary for this
game" from "this row predates the column" without paying for the request —
this script is that one deliberate payment, made once for every such row.

Safe to re-run: it skips any game that already has a description, so a second
run after a failure only picks up what the first one missed.

Usage (bot may keep running — HLTB and Anthropic are both unrelated to any
credential the bot holds open):
    .venv/Scripts/python.exe -X utf8 -m scripts.backfill_hltb_descriptions
    .venv/Scripts/python.exe -X utf8 -m scripts.backfill_hltb_descriptions --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from bot.config import get_settings
from bot.db.repo import Database, Repo
from bot.services.crypto import TokenCipher
from bot.services.hltb import _cache, _fetch_page_details, _from_cache_row, _translate
from bot.services.translate.auth import AnthropicAuth

logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("hltb-descriptions")

# Courtesy delay between requests to an endpoint with no official rate limit
# published — HLTB is not a service this project has any standing with.
# Same value scripts/backfill_hltb_platforms.py already uses.
REQUEST_DELAY_SECONDS = 1.0


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="fetch descriptions but neither translate nor write anything",
    )
    args = parser.parse_args()

    settings = get_settings()
    database = await Database(settings.db_path).connect()
    repo = Repo(database)
    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    anthropic_auth = AnthropicAuth(
        repo,
        cipher,
        env_key=(
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        ),
    )

    ids = await repo.hltb_all_ids()
    log.info("%s cached games to check", len(ids))

    filled = skipped = missing = 0
    for hltb_id in ids:
        row = await repo.hltb_get_cached(hltb_id)
        if row is None:  # pragma: no cover — the id list came from this table
            continue
        result = _from_cache_row(row)
        if result.description_en:
            skipped += 1
            continue
        if not result.game_url:
            log.warning("%s: %s has no HLTB page URL, skipped", hltb_id, result.name)
            missing += 1
            continue

        genre, description = await _fetch_page_details(result.game_url)
        await asyncio.sleep(REQUEST_DELAY_SECONDS)
        if not description:
            log.info("%s: %s — HLTB has no summary for it", hltb_id, result.name)
            missing += 1
            continue

        result.description_en = description
        # The genre may well have been missing too (it was added to the table
        # in migration 012, after some of these rows were written) and the
        # fetch already paid for it — no reason to throw it away.
        result.genre = result.genre or genre
        if args.dry_run:
            log.info("%s: %s — %s chars (dry run)", hltb_id, result.name, len(description))
            filled += 1
            continue

        result.description_ru = await _translate(description, anthropic_auth)
        await _cache(repo, result)
        filled += 1
        log.info(
            "%s: %s — %s chars, %s",
            hltb_id,
            result.name,
            len(description),
            "translated" if result.description_ru else "NOT translated",
        )

    log.info("done: %s filled, %s already had one, %s without a summary", filled, skipped, missing)
    await database.close()


if __name__ == "__main__":
    asyncio.run(main())
