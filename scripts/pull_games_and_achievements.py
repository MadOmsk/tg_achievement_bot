"""Bulk one-time synchronization: pull games, user achievements, and full achievement
catalog (`title_achievements`) into SQLite database.

Supports bootstrapping a brand new database by cloning user/account configurations
from an existing DB (--clone-users-from), or updating an existing database in place.

Safe to run on a test database first and then on production. Achievements are saved
with `is_backfill=True` and no announcements are ever sent to Telegram chats.

Usage:
    # 1. Test run on preview database with cloned users:
    .venv/Scripts/python.exe -m scripts.pull_games_and_achievements \\
        --env-file .env.test \\
        --db data/test_sync_preview.db \\
        --clone-users-from data/test.db \\
        --limit-titles 10

    # 2. Full run on production database:
    .venv/Scripts/python.exe -m scripts.pull_games_and_achievements \\
        --env-file .env \\
        --db data/bot.db
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiosqlite

from bot.config import Settings, get_settings
from bot.constants import Platform
from bot.db.repo import Database, Repo
from bot.poller.fetcher import Fetcher
from bot.poller.psn_fetcher import PsnFetcher
from bot.poller.steam_fetcher import SteamFetcher
from bot.services.crypto import TokenCipher
from bot.services.psn.auth import PsnAuth, PsnNotConfiguredError
from bot.services.steam.auth import SteamAuth, SteamNotConfiguredError
from bot.services.title_catalog import TitleCatalogService
from bot.services.translate.auth import AnthropicAuth
from bot.services.xbox.auth import XboxAuthService
from bot.services.xbox.client import XboxClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
# httpx logs request URLs at INFO, which can leak Steam API keys in query parameters
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("pull_sync")

TABLES_TO_CLONE = [
    "users",
    "accounts",
    "account_links",
    "tokens",
    "user_settings",
    "chats",
    "chat_settings",
    "subscriptions",
    "chat_seen",
    "app_settings",
]


class NoopPublisher:
    """Null publisher ensuring zero messages are sent to Telegram chats during sync."""

    async def publish(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def publish_flood_digest(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


@dataclass(slots=True)
class SyncConfig:
    target_db_path: Path
    clone_source_path: Path | None
    selected_platforms: set[str]
    user_ids: list[int] | None
    skip_achievements: bool
    skip_catalog: bool
    force: bool
    concurrency: int
    limit_titles: int | None
    translate: bool
    settings: Settings


async def clone_user_tables(source_path: Path, dest_conn: aiosqlite.Connection) -> dict[str, int]:
    """Clone user accounts, credentials, and settings from source database to destination."""
    stats: dict[str, int] = {}
    async with aiosqlite.connect(source_path) as src_conn:
        src_conn.row_factory = aiosqlite.Row
        await dest_conn.execute("PRAGMA foreign_keys = OFF")
        try:
            for table in TABLES_TO_CLONE:
                check_cur = await src_conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
                )
                if not await check_cur.fetchone():
                    continue

                cur = await src_conn.execute(f"SELECT * FROM {table}")
                rows = await cur.fetchall()
                if not rows:
                    stats[table] = 0
                    continue

                cols = [d[0] for d in cur.description]
                col_list = ", ".join(cols)
                placeholders = ", ".join(["?"] * len(cols))
                await dest_conn.executemany(
                    f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})",
                    [tuple(r) for r in rows],
                )
                stats[table] = len(rows)
            await dest_conn.commit()
        finally:
            await dest_conn.execute("PRAGMA foreign_keys = ON")
    return stats


def prepare_sync_config(settings: Settings | None = None) -> SyncConfig:
    parser = argparse.ArgumentParser(
        description="Bulk pull games, achievements, and title catalog into database."
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to .env file (default: BOT_ENV_FILE or .env)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to target SQLite database file (default: db_path from settings)",
    )
    parser.add_argument(
        "--clone-users-from",
        type=str,
        default=None,
        help="Path to source SQLite database to clone users/accounts/tokens from",
    )
    parser.add_argument(
        "--clean-target",
        action="store_true",
        help="Remove target database file if it already exists before running",
    )
    parser.add_argument(
        "--platforms",
        type=str,
        default="all",
        help="Platforms to sync: 'all', or comma-separated 'xbox,steam,psn' (default: all)",
    )
    parser.add_argument(
        "--users",
        type=str,
        default=None,
        help="Comma-separated Telegram user IDs to filter by (default: all users)",
    )
    parser.add_argument(
        "--skip-achievements",
        action="store_true",
        help="Skip backfilling user unlocked achievements (only fetch titles/games)",
    )
    parser.add_argument(
        "--skip-catalog",
        action="store_true",
        help="Skip filling full game achievement catalog (title_achievements)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force refresh title catalog even if within 24-hour debounce window",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Concurrency limit for catalog requests (default: 2)",
    )
    parser.add_argument(
        "--limit-titles",
        type=int,
        default=None,
        help="Limit number of titles for catalog sync (useful for testing)",
    )
    parser.add_argument(
        "--translate",
        action="store_true",
        help="Enable Anthropic LLM translations for missing descriptions (costs tokens)",
    )
    args = parser.parse_args()

    # 1. Environment & Settings configuration
    if settings is None:
        if args.env_file:
            env_path = Path(args.env_file).resolve()
            if not env_path.exists():
                log.error("Specified env file does not exist: %s", env_path)
                sys.exit(1)
            os.environ["BOT_ENV_FILE"] = str(env_path)
            get_settings.cache_clear()
            settings = Settings(_env_file=str(env_path))  # type: ignore[call-arg]
        else:
            settings = get_settings()

    target_db_path = Path(args.db).resolve() if args.db else settings.db_path.resolve()

    clone_source = None
    if args.clone_users_from:
        clone_source = Path(args.clone_users_from).resolve()
        if not clone_source.exists():
            log.error("Clone source DB does not exist: %s", clone_source)
            sys.exit(1)
        if clone_source == target_db_path:
            log.error("--clone-users-from cannot be identical to target --db (%s)", target_db_path)
            sys.exit(1)

    if args.clean_target and target_db_path.exists():
        log.info("Removing existing target database: %s", target_db_path)
        target_db_path.unlink(missing_ok=True)
        Path(f"{target_db_path}-wal").unlink(missing_ok=True)
        Path(f"{target_db_path}-shm").unlink(missing_ok=True)

    raw_plats = [p.strip().lower() for p in args.platforms.split(",") if p.strip()]
    if "all" in raw_plats:
        selected_platforms = {"xbox", "steam", "psn"}
    else:
        selected_platforms = set(raw_plats)

    user_ids = (
        [int(uid.strip()) for uid in args.users.split(",") if uid.strip()] if args.users else None
    )

    return SyncConfig(
        target_db_path=target_db_path,
        clone_source_path=clone_source,
        selected_platforms=selected_platforms,
        user_ids=user_ids,
        skip_achievements=args.skip_achievements,
        skip_catalog=args.skip_catalog,
        force=args.force,
        concurrency=args.concurrency,
        limit_titles=args.limit_titles,
        translate=args.translate,
        settings=settings,
    )


async def run_sync(cfg: SyncConfig) -> None:
    start_time = time.monotonic()
    log.info("Target database: %s", cfg.target_db_path)
    database = await Database(cfg.target_db_path).connect()
    repo = Repo(database)

    # 2. Optional user clone from existing DB
    if cfg.clone_source_path:
        log.info("Cloning user data from %s...", cfg.clone_source_path)
        cloned_counts = await clone_user_tables(cfg.clone_source_path, database.conn)
        for tbl, cnt in cloned_counts.items():
            log.info("  Cloned %s: %d rows", tbl, cnt)

    # 3. Initialize Services
    cipher = TokenCipher(cfg.settings.fernet_key.get_secret_value())
    auth = XboxAuthService(cfg.settings, repo, cipher)
    await auth.start()
    xbox_client = XboxClient(auth)

    steam_env_key = (
        cfg.settings.steam_api_key.get_secret_value() if cfg.settings.steam_api_key else None
    )
    steam_auth = SteamAuth(repo, cipher, env_key=steam_env_key)

    psn_auth = PsnAuth(repo, cipher)

    anthropic_env_key = (
        cfg.settings.anthropic_api_key.get_secret_value()
        if cfg.settings.anthropic_api_key
        else None
    )
    anthropic_auth = (
        AnthropicAuth(repo, cipher, env_key=anthropic_env_key) if cfg.translate else None
    )

    noop_pub = NoopPublisher()
    fetcher = Fetcher(
        repo,
        xbox_client,
        noop_pub,  # type: ignore[arg-type]
        concurrency=cfg.concurrency,
        anthropic_auth=anthropic_auth,
    )
    steam_fetcher = SteamFetcher(
        repo,
        steam_auth,
        noop_pub,  # type: ignore[arg-type]
        concurrency=cfg.concurrency,
        anthropic_auth=anthropic_auth,
    )
    psn_fetcher = PsnFetcher(
        cfg.settings,
        repo,
        psn_auth,
        noop_pub,  # type: ignore[arg-type]
        anthropic_auth=anthropic_auth,
    )
    catalog_service = TitleCatalogService(
        repo,
        xbox_client=xbox_client,
        psn_auth=psn_auth,
        steam_auth=steam_auth,
        anthropic_auth=anthropic_auth,
    )

    log.info(
        "Pulling data for platforms: %s (users: %s)",
        ", ".join(sorted(cfg.selected_platforms)),
        cfg.user_ids if cfg.user_ids else "all",
    )

    # ------------------------------------------------------------------
    # PHASE 1: User Games & Achievements
    # ------------------------------------------------------------------
    # 1.1 Xbox
    if "xbox" in cfg.selected_platforms:
        xbox_links = await repo.platform_links_all("xbox")
        if cfg.user_ids:
            xbox_links = [lnk for lnk in xbox_links if lnk.tg_id in cfg.user_ids]
        log.info("Found %d Xbox accounts to pull", len(xbox_links))
        for link in xbox_links:
            name = link.display_name or f"xuid={link.external_id}"
            log.info(
                "Processing Xbox for %s (tg_id=%d, xuid=%s)...",
                name,
                link.tg_id,
                link.external_id,
            )
            try:
                token = await repo.get_token(link.tg_id)
                if not token or token.status != "active":
                    log.warning(
                        "Xbox token for %s is %s, skipping",
                        name,
                        token.status if token else "missing",
                    )
                    continue

                if cfg.skip_achievements:
                    history = await xbox_client.title_history(link.tg_id, max_items=2000)
                    await fetcher._save_history(link.tg_id, link.external_id, history)
                    log.info("Xbox: saved %d titles for %s", len(history), name)
                else:
                    total_achs = await fetcher.backfill(link.tg_id, link.external_id)
                    log.info("Xbox: backfilled %d achievements for %s", total_achs, name)
                    try:
                        history = await xbox_client.title_history(link.tg_id, max_items=2000)
                        await fetcher._save_history(link.tg_id, link.external_id, history)
                        log.info(
                            "Xbox: deep title_history refreshed %d titles for %s",
                            len(history),
                            name,
                        )
                    except Exception as e:
                        log.warning("Xbox deep history failed for %s: %s", name, e)
            except Exception as exc:
                log.warning("Xbox pull failed for %s: %s", name, exc, exc_info=True)

    # 1.2 Steam
    if "steam" in cfg.selected_platforms:
        steam_links = await repo.platform_links_all("steam")
        if cfg.user_ids:
            steam_links = [lnk for lnk in steam_links if lnk.tg_id in cfg.user_ids]
        log.info("Found %d Steam accounts to pull", len(steam_links))
        for link in steam_links:
            name = link.display_name or f"steam_id={link.external_id}"
            log.info(
                "Processing Steam for %s (tg_id=%d, steam_id=%s)...",
                name,
                link.tg_id,
                link.external_id,
            )
            try:
                api_key = await steam_auth.require_key()
                if cfg.skip_achievements:
                    from bot.services.steam.client import get_owned_games

                    games = await get_owned_games(api_key, link.external_id)
                    for g in games:
                        await repo.upsert_title(str(g.appid), g.name, Platform.STEAM)
                    log.info("Steam: saved %d owned games for %s", len(games), name)
                else:
                    total_achs = await steam_fetcher.backfill(link.tg_id, link.external_id)
                    log.info("Steam: backfilled %d achievements for %s", total_achs, name)
            except SteamNotConfiguredError:
                log.warning("Steam is not configured (missing API key), skipping Steam sync")
                break
            except Exception as exc:
                log.warning("Steam pull failed for %s: %s", name, exc, exc_info=True)

    # 1.3 PSN
    if "psn" in cfg.selected_platforms:
        psn_links = await repo.platform_links_all("psn")
        if cfg.user_ids:
            psn_links = [lnk for lnk in psn_links if lnk.tg_id in cfg.user_ids]
        log.info("Found %d PSN accounts to pull", len(psn_links))
        for link in psn_links:
            name = link.display_name or f"account_id={link.external_id}"
            log.info(
                "Processing PSN for %s (tg_id=%d, account_id=%s)...",
                name,
                link.tg_id,
                link.external_id,
            )
            try:
                client = await psn_auth.get_client()
                if cfg.skip_achievements:
                    from bot.services.psn.client import trophy_titles

                    titles = await trophy_titles(client, link.external_id)
                    for t in titles:
                        await repo.upsert_title(
                            t.np_communication_id,
                            t.title_name,
                            Platform.PSN,
                            achievements_total=(
                                t.defined_trophies.total if t.defined_trophies else None
                            ),
                        )
                    log.info("PSN: saved %d trophy titles for %s", len(titles), name)
                else:
                    res = await psn_fetcher.backfill(link.tg_id, link.external_id)
                    log.info("PSN: backfilled %d trophies for %s", res.stored, name)
            except PsnNotConfiguredError:
                log.warning("PSN is not configured (missing NPSSO), skipping PSN sync")
                break
            except Exception as exc:
                log.warning("PSN pull failed for %s: %s", name, exc, exc_info=True)

    # ------------------------------------------------------------------
    # PHASE 2: Title Catalog Sync (title_achievements)
    # ------------------------------------------------------------------
    catalog_results = {"success": 0, "failed": 0, "achievements": 0}
    if not cfg.skip_catalog:
        cursor = await database.conn.execute(
            "SELECT title_id, platform, name FROM titles ORDER BY name"
        )
        all_titles = await cursor.fetchall()

        titles_to_sync: list[tuple[str, str, str]] = []
        for row in all_titles:
            t_id, t_plat, t_name = row["title_id"], row["platform"], row["name"]
            if "all" in cfg.selected_platforms:
                titles_to_sync.append((t_id, t_plat, t_name))
            elif "xbox" in cfg.selected_platforms and t_plat in ("xbox_modern", "xbox_360"):
                titles_to_sync.append((t_id, t_plat, t_name))
            elif "steam" in cfg.selected_platforms and t_plat == "steam":
                titles_to_sync.append((t_id, t_plat, t_name))
            elif "psn" in cfg.selected_platforms and t_plat == "psn":
                titles_to_sync.append((t_id, t_plat, t_name))

        if cfg.limit_titles:
            titles_to_sync = titles_to_sync[: cfg.limit_titles]

        total_titles = len(titles_to_sync)
        completed = 0
        lock = asyncio.Lock()
        catalog_start_time = time.monotonic()

        log.info(
            "Starting catalog sync for %d titles (concurrency=%d, force=%s)...",
            total_titles,
            cfg.concurrency,
            cfg.force,
        )

        sem = asyncio.Semaphore(max(1, cfg.concurrency))

        async def sync_one(tid: str, plat_str: str, title_title: str) -> None:
            nonlocal completed
            async with sem:
                try:
                    achs = await catalog_service.ensure_title_achievements_fresh(
                        plat_str,
                        tid,
                        force=cfg.force,
                    )
                    catalog_results["success"] += 1
                    catalog_results["achievements"] += len(achs)
                    ach_count = len(achs)
                except Exception as exc:
                    catalog_results["failed"] += 1
                    ach_count = 0
                    log.warning("Catalog [%s] %s (%s) failed: %s", plat_str, title_title, tid, exc)

                async with lock:
                    completed += 1
                    cur_completed = completed

                remaining = total_titles - cur_completed
                time_spent = time.monotonic() - catalog_start_time
                avg_rate = cur_completed / time_spent if time_spent > 0 else 0
                eta_sec = remaining / avg_rate if avg_rate > 0 else 0
                eta_min = int(eta_sec // 60)
                eta_rem_sec = int(eta_sec % 60)
                eta_str = f"{eta_min}m {eta_rem_sec}s" if avg_rate > 0 else "estimating..."

                log.info(
                    "Catalog [%d/%d, left: %d, ETA: %s] [%s] %s (%s): %d achs (ok=%d, fail=%d)",
                    cur_completed,
                    total_titles,
                    remaining,
                    eta_str,
                    plat_str,
                    title_title,
                    tid,
                    ach_count,
                    catalog_results["success"],
                    catalog_results["failed"],
                )
                await asyncio.sleep(0.1)

        await asyncio.gather(*(sync_one(t[0], t[1], t[2]) for t in titles_to_sync))

    # ------------------------------------------------------------------
    # PHASE 3: Summary Report
    # ------------------------------------------------------------------
    elapsed = time.monotonic() - start_time
    cur = await database.conn.execute("SELECT COUNT(*) FROM users")
    total_users = (await cur.fetchone())[0]

    cur = await database.conn.execute("SELECT platform, COUNT(*) FROM accounts GROUP BY platform")
    acc_rows = await cur.fetchall()
    acc_summary = ", ".join(f"{r[0]}: {r[1]}" for r in acc_rows) or "0"

    cur = await database.conn.execute("SELECT platform, COUNT(*) FROM titles GROUP BY platform")
    title_rows = await cur.fetchall()
    titles_summary = ", ".join(f"{r[0]}: {r[1]}" for r in title_rows) or "0"

    cur = await database.conn.execute("SELECT COUNT(*) FROM seen_achievements")
    total_seen = (await cur.fetchone())[0]

    cur = await database.conn.execute(
        "SELECT platform, COUNT(*) FROM title_achievements GROUP BY platform"
    )
    cat_rows = await cur.fetchall()
    cat_summary = ", ".join(f"{r[0]}: {r[1]}" for r in cat_rows) or "0"

    log.info("=" * 60)
    log.info("PULL SYNCHRONIZATION SUMMARY REPORT")
    log.info("=" * 60)
    log.info("Target DB:               %s", cfg.target_db_path)
    log.info("Elapsed time:            %.2f seconds", elapsed)
    log.info("Total users in DB:       %d", total_users)
    log.info("Accounts in DB:          %s", acc_summary)
    log.info("Titles in DB:            %s", titles_summary)
    log.info("Seen achievements:       %d", total_seen)
    log.info("Title catalog entries:   %s", cat_summary)
    if not cfg.skip_catalog:
        log.info(
            "Catalog sync results:    %d succeeded, %d failed (%d achievements loaded)",
            catalog_results["success"],
            catalog_results["failed"],
            catalog_results["achievements"],
        )
    log.info("=" * 60)

    # Clean shutdown
    await auth.close()
    await database.close()


def main() -> None:
    cfg = prepare_sync_config()
    asyncio.run(run_sync(cfg))


if __name__ == "__main__":
    main()
