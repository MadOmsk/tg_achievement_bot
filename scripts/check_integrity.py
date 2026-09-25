"""Is every achievement the platforms know about in the database? (#120)

Compares, per linked account, what the platform itself says a person has
earned with what the bot has stored — the answer to "how deep did the history
go", measured rather than assumed. Read-only everywhere:

* the database is opened with sqlite's own read-only mode, never through
  `Database.connect()` — that applies migrations, which is how a script once
  took production down (#56);
* **Xbox** is compared against the profile gamerscore the poller already
  caches (`accounts.gamerscore`) and makes no request: Xbox answers only
  through a person's own refresh token, which rotates, and a second process
  refreshing it logs that person out;
* **PSN** asks Sony, through the shared NPSSO, for each account's trophy
  summary and its per-game list — two requests per account;
* **Steam** asks, through the shared key, for each account's whole library
  (free-to-play and never-launched games included) and then one request per
  game that has achievements — the only way: Steam keeps no total.

Credentials come from the database the env file points at; the data from
`--db` when given, so a copy of production can be checked with the dev
server's own keys:

    python scripts/check_integrity.py --env-file .env.test --db backups/bot-copy.db
    python scripts/check_integrity.py --platform psn            # on a server

Exit code 1 when anything is missing.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.config import Settings
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import NPSSO_KEY
from bot.services.psn.client import build_client
from bot.services.steam import client as steam
from bot.services.steam.auth import KEY_ENC_KEY

logging.basicConfig(level=logging.WARNING, format="%(levelname)-7s %(message)s")
log = logging.getLogger("check_integrity")

# Steam requests at once: politeness toward a shared key, not a limit.
STEAM_CONCURRENCY = 4


@dataclass(slots=True)
class Report:
    missing: int = 0
    lines: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        self.lines.append(line)
        print(line, flush=True)


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _accounts(data: sqlite3.Connection, platform: str) -> list[sqlite3.Row]:
    return data.execute(
        "SELECT a.display_name, a.external_id, a.gamerscore FROM accounts a "
        "JOIN account_links al ON al.platform = a.platform AND al.external_id = a.external_id"
        " AND al.is_active = 1 "
        "WHERE a.platform = ? ORDER BY a.display_name",
        (platform,),
    ).fetchall()


def _secret(creds: sqlite3.Connection, cipher: TokenCipher, key: str) -> str | None:
    row = creds.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if row is None or not row["value"]:
        return None
    try:
        return cipher.decrypt(row["value"].encode("ascii"))
    except ValueError:
        log.warning("%s cannot be decrypted with this FERNET_KEY", key)
        return None


# ------------------------------------------------------------------ Xbox


def check_xbox(data: sqlite3.Connection, report: Report) -> None:
    report.say("== Xbox: profile gamerscore (cached from the API) vs stored achievements")
    for account in _accounts(data, "xbox"):
        stored, count = data.execute(
            "SELECT COALESCE(SUM(gamerscore), 0), COUNT(*) FROM seen_achievements "
            "WHERE account_platform = 'xbox' AND xuid = ?",
            (account["external_id"],),
        ).fetchone()
        profile = account["gamerscore"]
        if profile is None:
            report.say(f"  {account['display_name']}: no profile gamerscore cached yet")
            continue
        gap = profile - stored
        mark = "ok" if gap == 0 else f"MISSING {gap} G"
        report.say(
            f"  {account['display_name']:24} profile {profile:>7} | stored {stored:>7}"
            f" ({count} achievements) | {mark}"
        )
        if gap > 0:
            report.missing += 1


# ------------------------------------------------------------------- PSN


async def check_psn(data: sqlite3.Connection, npsso: str | None, report: Report) -> None:
    report.say("== PSN: Sony's trophy summary and per-game lists vs stored trophies")
    if not npsso:
        report.say("  skipped: no NPSSO configured")
        return
    client = await build_client(npsso)
    for account in _accounts(data, "psn"):
        name, account_id = account["display_name"], account["external_id"]
        try:
            user = await asyncio.to_thread(client.user, account_id=account_id)
            summary = await asyncio.to_thread(user.trophy_summary)
            titles = await asyncio.to_thread(lambda u=user: list(u.trophy_titles(limit=None)))
        except Exception as exc:  # a private profile, a dead token: report, go on
            report.say(f"  {name}: Sony did not answer ({exc!r})")
            continue
        earned = summary.earned_trophies
        sony_total = earned.bronze + earned.silver + earned.gold + earned.platinum
        stored_total = data.execute(
            "SELECT COUNT(*) FROM seen_achievements WHERE account_platform = 'psn' AND xuid = ?",
            (account_id,),
        ).fetchone()[0]
        gap = sony_total - stored_total
        report.say(
            f"  {name:24} Sony {sony_total:>5} | stored {stored_total:>5} | "
            + ("ok" if gap == 0 else f"MISSING {gap}")
        )
        if gap > 0:
            report.missing += 1
        for title in titles:
            got = title.earned_trophies
            sony = got.bronze + got.silver + got.gold + got.platinum
            stored, grouped = data.execute(
                "SELECT COUNT(*), COUNT(trophy_group_id) FROM seen_achievements "
                "WHERE account_platform = 'psn' AND xuid = ? AND title_id = ?",
                (account_id, title.np_communication_id),
            ).fetchone()
            if sony != stored:
                why = (
                    "nothing stored"
                    if stored == 0
                    else "stored before #46, DLC never fetched"
                    if grouped == 0
                    else ""
                )
                report.say(
                    f"      {(title.title_name or '?')[:40]:40} {title.np_communication_id}"
                    f" Sony {sony} stored {stored}" + (f" — {why}" if why else "")
                )


# ----------------------------------------------------------------- Steam


async def _steam_game(key: str, steam_id: str, appid: str, slots: asyncio.Semaphore) -> int | None:
    async with slots:
        try:
            achievements = await steam.get_player_achievements(key, steam_id, appid)
        except Exception as exc:
            log.info("steam %s/%s: %r", steam_id, appid, exc)
            return None
    return sum(1 for a in achievements if a.achieved)


async def check_steam(data: sqlite3.Connection, key: str | None, report: Report) -> None:
    report.say("== Steam: every game in the library vs stored achievements")
    if not key:
        report.say("  skipped: no Steam key configured")
        return
    slots = asyncio.Semaphore(STEAM_CONCURRENCY)
    for account in _accounts(data, "steam"):
        name, steam_id = account["display_name"], account["external_id"]
        try:
            # Not steam.get_owned_games: that one keeps only games with
            # playtime, which is one of the gaps this is meant to measure.
            payload = await steam._get(
                "/IPlayerService/GetOwnedGames/v1/",
                key,
                {
                    "steamid": steam_id,
                    "include_appinfo": "1",
                    "include_played_free_games": "1",
                },
            )
        except Exception as exc:
            report.say(f"  {name}: Steam did not answer ({exc!r})")
            continue
        if "games" not in payload:
            report.say(f"  {name}: game details are private")
            continue
        games = [g for g in payload["games"] if g.get("has_community_visible_stats")]
        games += [
            {"appid": appid, "name": name, "playtime_forever": g.get("playtime_forever")}
            for g in games
            for appid, name in steam.FOLDED_APPS.get(str(g["appid"]), ())
        ]
        counts = await asyncio.gather(
            *(_steam_game(key, steam_id, str(g["appid"]), slots) for g in games)
        )
        stored_by_app = dict(
            data.execute(
                "SELECT title_id, COUNT(*) FROM seen_achievements "
                "WHERE account_platform = 'steam' AND xuid = ? GROUP BY title_id",
                (steam_id,),
            ).fetchall()
        )
        steam_total = stored_total = unanswered = 0
        gaps: list[str] = []
        for game, count in zip(games, counts, strict=True):
            appid = str(game["appid"])
            stored = stored_by_app.get(appid, 0)
            stored_total += stored
            if count is None:
                unanswered += 1
                continue
            steam_total += count
            if count != stored:
                playtime = int(game.get("playtime_forever") or 0)
                why = "never launched per Steam — backfill skips it" if playtime == 0 else ""
                gaps.append(
                    f"      {(game.get('name') or appid)[:40]:40} {appid:>8}"
                    f" Steam {count} stored {stored}" + (f" — {why}" if why else "")
                )
        gap = steam_total - stored_total
        report.say(
            f"  {name:24} Steam {steam_total:>5} | stored {stored_total:>5} | "
            + ("ok" if gap == 0 else f"MISSING {gap}")
            + f" ({len(games)} games with stats"
            + (f", {unanswered} unanswered" if unanswered else "")
            + ")"
        )
        if gap > 0:
            report.missing += 1
        for line in gaps:
            report.say(line)


# ------------------------------------------------------------------ main


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--env-file", default=".env", help="credentials (default: .env)")
    parser.add_argument("--db", type=Path, help="data to check (default: the env file's DB)")
    parser.add_argument("--platform", choices=["all", "xbox", "psn", "steam"], default="all")
    args = parser.parse_args()

    settings = Settings(_env_file=args.env_file)
    cipher = TokenCipher(settings.fernet_key.get_secret_value())
    creds = _open_ro(Path(settings.db_path))
    data = _open_ro(args.db) if args.db else creds
    report = Report()

    if args.platform in ("all", "xbox"):
        check_xbox(data, report)
    if args.platform in ("all", "psn"):
        await check_psn(data, _secret(creds, cipher, NPSSO_KEY), report)
    if args.platform in ("all", "steam"):
        key = _secret(creds, cipher, KEY_ENC_KEY) or (
            settings.steam_api_key.get_secret_value() if settings.steam_api_key else None
        )
        await check_steam(data, key, report)

    print(f"\n{report.missing} account(s) with something missing")
    return 1 if report.missing else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
