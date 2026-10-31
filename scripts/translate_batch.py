"""A share of the translators' queue now, step by step, and what it costs in tokens.

Prints the running total after every step, so a run stopped halfway still says what
it spent, and stops by itself past `--max-dollars`. The bot's own queue being off
(its default), nothing else spends beside it but a page somebody opens.

    python -X utf8 -m scripts.translate_batch --games 380 --posts 125 --max-dollars 1
"""

from __future__ import annotations

import argparse
import time

from bot.config import get_settings
from bot.db import tools
from bot.db.repo import Repo
from bot.poller.translations import Translations
from bot.services.crypto import TokenCipher
from bot.services.game_descriptions import GameTranslator
from bot.services.guide_translations import GuideTranslator
from bot.services.news_translations import NewsTranslator
from bot.services.translate import client
from bot.services.translate.auth import AnthropicAuth

# Haiku 5.5, dollars per token.
INPUT_PRICE = 0.10 / 1_000_000
OUTPUT_PRICE = 0.50 / 1_000_000
STEP_GAMES = 20
STEP_POSTS = 10


def dollars() -> float:
    return client.spent_tokens["input"] * INPUT_PRICE + client.spent_tokens["output"] * OUTPUT_PRICE


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        auth = AnthropicAuth(repo, TokenCipher(settings.fernet_key.get_secret_value()))
        news = NewsTranslator(repo, auth)
        guides = GuideTranslator(repo, auth)
        queue = Translations(repo, news, guides, GameTranslator(repo, auth, guides, news))
        started = time.monotonic()
        games, posts = 0, 0
        while games < args.games or posts < args.posts:
            took = await queue.batch(
                min(STEP_GAMES, max(args.games - games, 0)),
                min(STEP_POSTS, max(args.posts - posts, 0)),
            )
            games += took["games"]
            posts += took["posts"]
            print(
                f"games {games} posts {posts} guides {took['guides']}"
                f" tokens in {client.spent_tokens['input']} out {client.spent_tokens['output']}"
                f" ${dollars():.3f} {time.monotonic() - started:.0f} s",
                flush=True,
            )
            if dollars() >= args.max_dollars:
                print("stopped: the limit in dollars", flush=True)
                break
            if not took["games"] and not took["posts"] and not took["guides"]:
                print("stopped: nothing left", flush=True)
                break
    finally:
        await database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--games", type=int, default=0)
    parser.add_argument("--posts", type=int, default=0)
    parser.add_argument("--max-dollars", type=float, default=1.0)
    tools.add_arguments(parser)
    tools.run(main(parser.parse_args()))
