"""One batch of the translators' queue now, and what it cost in tokens.

For measuring a share of the queue against the account's balance: switch the bot's
own queue off first (`translation_batch_games` = 0), or it spends beside this.

    python -X utf8 -m scripts.translate_batch --games 380 --posts 120 [--schema test]
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


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    database = await tools.open_database(schema=args.schema)
    try:
        repo = Repo(database)
        auth = AnthropicAuth(repo, TokenCipher(settings.fernet_key.get_secret_value()))
        news = NewsTranslator(repo, auth)
        guides = GuideTranslator(repo, auth)
        games = GameTranslator(repo, auth, guides, news)
        started = time.monotonic()
        took = await Translations(repo, news, guides, games).batch(args.games, args.posts)
        print(f"took {took} in {time.monotonic() - started:.0f} s")
        print(f"tokens in {client.spent_tokens['input']}, out {client.spent_tokens['output']}")
    finally:
        await database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--games", type=int, default=0)
    parser.add_argument("--posts", type=int, default=0)
    tools.add_arguments(parser)
    tools.run(main(parser.parse_args()))
