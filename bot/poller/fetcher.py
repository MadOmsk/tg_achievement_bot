"""Fetching achievements, deduplication and backfill (SPEC 5.3, 5.4, 5.6)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from bot.constants import AccountPlatform, Platform, PresenceState
from bot.db.repo import AchievementRow, Repo, TitleAchievementRow, TitleHistoryRow
from bot.i18n import translator
from bot.poller.publisher import Publisher
from bot.services import achievement_icons
from bot.services.platform_format import game_platforms_json
from bot.services.rows import to_achievement_row
from bot.services.translate.auth import AnthropicAuth
from bot.services.translate.descriptions import bilingual_descriptions
from bot.services.xbox.auth import TokenRefreshError
from bot.services.xbox.client import TitleHistoryEntry, XboxApiError, XboxClient
from bot.services.xbox.models import ParsedAchievement
from bot.util import parse_iso, utcnow, utcnow_iso

log = logging.getLogger(__name__)

# How far back backfill reads the title history (#121). Microsoft answers a
# thousand-title account inside title_history's own deadline (~46s measured).
BACKFILL_HISTORY_ITEMS = 2000


class Fetcher:
    def __init__(
        self,
        repo: Repo,
        client: XboxClient,
        publisher: Publisher,
        concurrency: int = 2,
        *,
        anthropic_auth: AnthropicAuth,
    ) -> None:
        self._repo = repo
        self._client = client
        self._publisher = publisher
        self._anthropic_auth = anthropic_auth
        self._backfill_slots = asyncio.Semaphore(concurrency)
        self._background_tasks: set[asyncio.Task[None]] = set()
        # Titles every contract answered empty for — apps, and PC titles
        # without achievements, that presence still reports as being played
        # (#122). Asked once per process: without this each costs three
        # requests every achievement debounce for as long as somebody is in it.
        self._no_achievements: set[str] = set()

    def api_usage(self) -> list[tuple[int, int, float]]:
        """(used, limit, window_seconds) — surfaced in the admin panel
        (SPEC 6.4) so "are we anywhere near a limit" has an actual answer."""
        return self._client.rate_limit_usage()

    async def poll_title(
        self,
        tg_id: int,
        xuid: str,
        gamertag: str,
        title_id: str,
        platform: Platform,
        title_name: str | None,
        device: str | None = None,
    ) -> int:
        """Fetch one game's achievements, keep the new ones, publish them."""
        # Presence sometimes reports a title id of 0 — no game at all (#122).
        if not title_id or title_id == "0" or title_id in self._no_achievements:
            return 0
        parsed, total = await self._client.title_achievements_with_total(tg_id, title_id, platform)
        if not parsed and not total:
            # Not "nothing new": nothing listed by any contract, so the title
            # has no achievements to earn (a game always lists its whole set).
            log.info("title %s has no achievements, not asking again", title_id)
            self._no_achievements.add(title_id)
            return 0
        # The size of the set those unlocks came from — the "47/50" counter's
        # own denominator (#46). titlehub reports it for Xbox 360 and returns
        # 0 for most modern titles, so for those this response is the only
        # place it exists; `upsert_title` never blanks a total it already
        # knows, so a reply that does not say leaves the stored one alone.
        if total:
            if title_name:
                await self._repo.upsert_title(
                    title_id, title_name, platform, achievements_total=total
                )
            else:
                # Presence gives no name for a PC title; the name is resolved
                # further down, and the total must not wait for it.
                await self._repo.set_title_total(title_id, total)
        await self._fill_x360_icon(tg_id, title_id, platform, parsed)
        await self._bilingual_descriptions(tg_id, title_id, platform, parsed)
        # Free: this response carried the percentages, and the shared cache is
        # what an older row without one reads instead (poller/rarity_backfill.py).
        await self._repo.cache_rarity(
            platform,
            title_id,
            {a.achievement_id: a.rarity_percent for a in parsed if a.rarity_percent is not None},
        )
        self._pre_cache_icons(platform, title_id, parsed)
        rows = [to_achievement_row(item, device=device) for item in parsed]
        new_rows = await self._repo.insert_new_achievements(xuid, rows, is_backfill=False)
        await self._repo.mark_achievements_polled(xuid)
        if not new_rows:
            return 0

        log.info("tg_id=%s unlocked %s new achievements in %s", tg_id, len(new_rows), title_id)
        resolved = await self.ensure_title_name(tg_id, title_id, title_name)
        await self.ensure_title_platforms(tg_id, title_id)
        await self._publisher.publish(tg_id, xuid, gamertag, new_rows, resolved)
        return len(new_rows)

    async def ensure_title_name(
        self, tg_id: int, title_id: str, from_presence: str | None
    ) -> str | None:
        """Presence leaves the name empty for PC titles, so ask titlehub once.

        "неизвестная игра" in a published message is worse than one extra
        request per game we have never seen.
        """
        if from_presence:
            return from_presence
        cached = await self._repo.title_name(title_id)
        if cached:
            return cached
        try:
            entry = await self._client.resolve_title(tg_id, title_id)
        except XboxApiError as exc:
            log.info("could not resolve title %s: %s", title_id, exc)
            return None
        if entry is None or not entry.name:
            return None
        platforms_json = game_platforms_json(
            entry.devices, is_x360=entry.platform == Platform.XBOX_360
        )
        await self._repo.upsert_title(
            entry.title_id, entry.name, entry.platform, platforms=platforms_json
        )
        return entry.name

    async def ensure_title_platforms(self, tg_id: int, title_id: str) -> None:
        """A game's platforms before its achievements are announced (#114):
        they decide which version of the game the card names, and without
        them a Smart Delivery or Play Anywhere game can only say "XBOX".

        Asked only while the lookup is due (repo.platforms_lookup_due): an
        answer is stored for good, and three failures stop the asking —
        the card then names the version native to the device played on.
        poller/title_platforms.py works through the games nobody is
        publishing in.
        """
        if not await self._repo.platforms_lookup_due(title_id):
            return
        try:
            entry = await self._client.resolve_title(tg_id, title_id)
        except (XboxApiError, TokenRefreshError) as exc:
            log.info("could not look up platforms of title %s: %s", title_id, exc)
            entry = None
        found = (
            game_platforms_json(entry.devices, is_x360=entry.platform == Platform.XBOX_360)
            if entry
            else None
        )
        await self._repo.record_platforms_lookup(title_id, found)

    async def ensure_title_icon(self, tg_id: int, title_id: str) -> str | None:
        """Box art as a stand-in for an Xbox 360 achievement icon (SPEC 7.1)
        — contract 1's achievement payload only ever carries a bare imageId
        int, no documented way to turn it into a URL at all (verified live
        against the real API: the raw response has nothing image-shaped
        besides that number). No `from_presence` shortcut like
        ensure_title_name has — presence never carries box art either way.
        """
        cached = await self._repo.title_icon_url(title_id)
        if cached:
            return cached
        try:
            entry = await self._client.resolve_title(tg_id, title_id)
        except XboxApiError as exc:
            log.info("could not resolve icon for title %s: %s", title_id, exc)
            return None
        if entry is None or not entry.icon_url:
            return None
        await self._repo.upsert_title(entry.title_id, entry.name, entry.platform, entry.icon_url)
        return entry.icon_url

    async def _fill_x360_icon(
        self, tg_id: int, title_id: str, platform: Platform, parsed: list[ParsedAchievement]
    ) -> None:
        """Shared by poll_title() and catch_up() — both publish live x360
        unlocks and must agree on the icon. If an achievement has no genuine icon,
        fall back to the game's box art."""
        if platform != Platform.XBOX_360:
            return
        missing = [item for item in parsed if not item.icon_url]
        if not missing:
            return
        icon_url = await self.ensure_title_icon(tg_id, title_id)
        if icon_url:
            for item in missing:
                item.icon_url = icon_url

    def _pre_cache_icons(
        self, platform: Platform, title_id: str, parsed: list[ParsedAchievement]
    ) -> None:
        plat_str = platform.value if hasattr(platform, "value") else str(platform)
        for item in parsed:
            if item.icon_url:
                task = asyncio.create_task(
                    achievement_icons.pre_cache_icon(
                        plat_str, title_id, item.achievement_id, item.icon_url
                    )
                )
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)

    async def _bilingual_descriptions(
        self, tg_id: int, title_id: str, platform: Platform, parsed: list[ParsedAchievement]
    ) -> None:
        """Mutates each item's `.description` in place — same shape
        `_fill_x360_icon` above already uses. Only called from poll_title/
        catch_up (2026-09-09): both are the only two paths that actually
        publish what they fetch here — backfill's own x360 pass (below)
        deliberately skips this, translating history nobody will ever see
        would just be wasted API/LLM cost for nothing.

        A second `ru-RU` request, only for achievements not already in
        the catalog — once every achievement in a game
        has been seen once, from any account, this never runs again for
        it. Xbox's own English text is left as `.description` for anything
        the bilingual lookup couldn't resolve (no cache hit and the second
        request came back empty/failed) — same "degrade to the language
        already fetched" shape services/steam/achievements.py's own
        version of this uses.
        """
        candidates = {item.achievement_id: item.description for item in parsed if item.description}
        # A name is worth the second request on its own (#61): a game whose
        # descriptions were all cached before names existed would otherwise
        # never ask for Russian again, and would keep showing English names in
        # a Russian chat forever.
        nameless = await self._repo.names_missing(
            platform, title_id, [item.achievement_id for item in parsed]
        )
        if not candidates and not nameless:
            return

        plat_str = platform.value if hasattr(platform, "value") else str(platform)
        catalog = await self._repo.get_title_achievements(plat_str, title_id)
        cat_by_id = {row.achievement_id: row for row in catalog} if catalog else {}

        result: dict[str, tuple[str | None, str | None]] = {}
        uncached: dict[str, str] = {}
        for achievement_id, english_text in candidates.items():
            cat_row = cat_by_id.get(achievement_id)
            if cat_row and cat_row.description_ru:
                result[achievement_id] = (
                    cat_row.description_ru,
                    cat_row.description_en or english_text,
                )
                continue
            cached = await self._repo.get_cached_description(platform, title_id, achievement_id)
            if cached is not None:
                result[achievement_id] = (cached.description_ru, cached.description_en)
            else:
                uncached[achievement_id] = english_text

        if nameless and catalog:
            nameless = [
                aid for aid in nameless if aid not in cat_by_id or not cat_by_id[aid].name_ru
            ]

        if uncached or nameless:
            try:
                russian_parsed = await self._client.title_achievements(
                    tg_id, title_id, platform, language="ru-RU"
                )
            except XboxApiError as exc:
                log.info("bilingual fetch for title %s skipped: %s", title_id, exc)
                russian_parsed = []
            # The same response carries the names, and they cost nothing more
            # (#61). `parsed` is the en-US answer, `russian_parsed` the ru-RU
            # one, so this is the platform's own pair — never a translation.
            english_names = {item.achievement_id: item.name for item in parsed}
            await self._repo.cache_names(
                platform,
                title_id,
                {
                    item.achievement_id: (item.name, english_names.get(item.achievement_id))
                    for item in russian_parsed
                },
            )
            # Xbox localizes a game's own title too, for games that have a
            # Russian name — "Halo: The Master Chief Collection" comes back as
            # "Halo: Коллекция Мастер Чифа" (#61). Contract 4 carries it on
            # every achievement; contract 1 (x360) carries none, and then
            # there is simply nothing to store.
            await self._repo.set_title_names(
                title_id,
                next((item.title_name for item in russian_parsed if item.title_name), None),
                next((item.title_name for item in parsed if item.title_name), None),
            )
            russian_by_id = {item.achievement_id: item.description for item in russian_parsed}
            native = {
                achievement_id: (russian_text, english_text)
                for achievement_id, english_text in uncached.items()
                if (russian_text := russian_by_id.get(achievement_id)) is not None
            }
            if native:
                resolved = await bilingual_descriptions(
                    self._repo, self._anthropic_auth, platform, title_id, native
                )
                result.update(resolved)

            now = utcnow_iso()
            ru_names = {item.achievement_id: item.name for item in russian_parsed}
            cat_rows = [
                TitleAchievementRow(
                    platform=plat_str,
                    title_id=title_id,
                    achievement_id=item.achievement_id,
                    name_ru=ru_names.get(item.achievement_id, item.name),
                    name_en=item.name,
                    description_ru=result.get(item.achievement_id, (None, None))[0],
                    description_en=item.description,
                    icon_url=item.icon_url,
                    is_secret=item.is_secret,
                    gamerscore=item.gamerscore,
                    rarity_percent=item.rarity_percent,
                    updated_at=now,
                )
                for item in parsed
            ]
            await self._repo.upsert_title_achievements(cat_rows)

        for item in parsed:
            resolved_pair = result.get(item.achievement_id)
            if resolved_pair is not None and resolved_pair[0] is not None:
                item.description = resolved_pair[0]

    async def backfill(self, tg_id: int, xuid: str) -> int:
        """Mark everything already unlocked as seen, publishing nothing.

        Without this the first poll after connecting would dump thousands of
        old achievements into the chat.
        """
        async with self._backfill_slots:
            raw_items = await self._client.all_achievements(tg_id)
            rows = [to_achievement_row(item) for item in raw_items]

            # Save any titles learned from all_achievements (contract 2) so older
            # games beyond title_history's window don't stay untitled in the catalog (#77).
            for item in raw_items:
                if item.title_id and item.title_name:
                    await self._repo.upsert_title(
                        item.title_id, item.title_name, item.platform or Platform.XBOX_MODERN
                    )

            # Contract 2 covers modern titles only — verified against a live
            # account, where an Xbox 360 game with 33 unlocked achievements was
            # absent from the full list. Without this second pass the first
            # session in such a game would look like 33 fresh unlocks.
            # The whole history, not the 200 most recent the pollers read:
            # an Xbox 360 game is found only here, and a long-standing account
            # has hundreds — 342 of 1096 titles on one, of which the default
            # window held 13 (#121).
            history = await self._client.title_history(tg_id, max_items=BACKFILL_HISTORY_ITEMS)
            for entry in history:
                if entry.platform != Platform.XBOX_360:
                    continue
                try:
                    parsed = await self._client.title_achievements(
                        tg_id, entry.title_id, Platform.XBOX_360
                    )
                except XboxApiError as exc:
                    log.info("x360 backfill of %s skipped: %s", entry.title_id, exc)
                    continue
                await self._repo.cache_rarity(
                    Platform.XBOX_360,
                    entry.title_id,
                    {
                        a.achievement_id: a.rarity_percent
                        for a in parsed
                        if a.rarity_percent is not None
                    },
                )
                rows.extend(to_achievement_row(item) for item in parsed)

            await self._repo.insert_new_achievements(xuid, rows, is_backfill=True)
            await self._save_history(tg_id, xuid, history)
            log.info("backfill for tg_id=%s stored %s achievements", tg_id, len(rows))
            return len(rows)

    async def catch_up(
        self,
        tg_id: int,
        xuid: str,
        gamertag: str,
        since: datetime | None,
        window_hours: int,
        max_titles: int,
    ) -> tuple[int, int]:
        """Pick up what was unlocked while the bot was down (SPEC 5.8).

        Only achievements newer than the window reach the chat. Older ones are
        still recorded, just not announced: after a fortnight of downtime a
        chat does not want the archive, and after a one-minute restart nothing
        should be lost.
        """
        async with self._backfill_slots:
            history = await self._client.title_history(tg_id)
            await self._save_history(tg_id, xuid, history)

            candidates = _played_since(history, since)[:max_titles]
            if not candidates:
                return 0, 0

            publish_after = utcnow() - timedelta(hours=window_hours)
            published = 0
            for entry in candidates:
                try:
                    parsed = await self._client.title_achievements(
                        tg_id, entry.title_id, entry.platform
                    )
                except XboxApiError as exc:
                    log.info("catch-up skipped title %s: %s", entry.title_id, exc)
                    continue
                await self._fill_x360_icon(tg_id, entry.title_id, entry.platform, parsed)
                await self._bilingual_descriptions(tg_id, entry.title_id, entry.platform, parsed)
                await self._repo.cache_rarity(
                    entry.platform,
                    entry.title_id,
                    {
                        a.achievement_id: a.rarity_percent
                        for a in parsed
                        if a.rarity_percent is not None
                    },
                )
                self._pre_cache_icons(entry.platform, entry.title_id, parsed)

                new_rows = await self._repo.insert_new_achievements(
                    xuid, [to_achievement_row(item) for item in parsed], is_backfill=False
                )
                fresh = [
                    row
                    for row in new_rows
                    if _publishable(row, publish_after, entry.last_played_at)
                ]
                if fresh:
                    await self.ensure_title_platforms(tg_id, entry.title_id)
                    await self._publisher.publish(tg_id, xuid, gamertag, fresh, entry.name)
                    published += len(fresh)

            log.info(
                "catch-up for tg_id=%s: %s titles, %s published",
                tg_id,
                len(candidates),
                published,
            )
            return len(candidates), published

    async def refresh_user(self, tg_id: int, xuid: str, gamertag: str, locale: str) -> str:
        """An out-of-turn look at one person, for the admin card (SPEC 6.4).

        The only on-demand API call in the interface, so it does the whole
        round: presence, the current game's achievements, title history.
        """
        _ = translator("fetcher", locale)
        snapshot = await self._client.presence(tg_id)
        await self._repo.save_presence_state(
            xuid,
            snapshot.state,
            snapshot.title_id,
            snapshot.title_name,
            device=snapshot.device,
            changed=False,
        )

        published = 0
        if snapshot.in_game and snapshot.title_id:
            published = await self.poll_title(
                tg_id,
                xuid,
                gamertag,
                snapshot.title_id,
                snapshot.platform,
                snapshot.title_name,
                device=snapshot.device,
            )
        await self.refresh_title_history(tg_id, xuid)

        where = snapshot.title_name or snapshot.title_id or _("fetcher-no-game")
        state = (
            _("fetcher-online", where=where)
            if snapshot.state == PresenceState.ONLINE
            else _("fetcher-offline")
        )
        return _("fetcher-refreshed", state=state, published=published)

    async def refresh_title_history(self, tg_id: int, xuid: str) -> None:
        """Source of /stats, /top and of the gamerscore in the panel (SPEC 5.4)."""
        await self._save_history(tg_id, xuid, await self._client.title_history(tg_id))

    async def _save_history(self, tg_id: int, xuid: str, history: list) -> None:
        rows = [
            TitleHistoryRow(
                title_id=entry.title_id,
                name=entry.name,
                platform=entry.platform,
                current_gamerscore=entry.current_gamerscore,
                max_gamerscore=entry.max_gamerscore,
                achievements_unlocked=entry.achievements_unlocked,
                achievements_total=entry.achievements_total,
                last_played_at=entry.last_played_at,
                devices=getattr(entry, "devices", None) or [],
            )
            for entry in history
        ]
        if not rows:
            return
        await self._repo.save_title_history(xuid, rows)

        # From the profile, not from the sum above: the title history request is
        # capped, so an account with more games than the cap would show too low
        # a score.
        try:
            snapshot = await self._client.profile(tg_id)
        except XboxApiError as exc:
            log.info("profile for tg_id=%s not refreshed: %s", tg_id, exc)
            return
        if snapshot.gamerscore is not None:
            await self._repo.update_gamerscore(tg_id, snapshot.gamerscore)
        # The gamertags came in the same response (#51). Xbox used to store
        # them once at connect and never again, so a rename left the bot
        # calling someone by an old name and pointing at a dead profile
        # link — both Xbox links are built from the nickname, not the XUID.
        if snapshot.gamertag or snapshot.gamertag_modern:
            await self._repo.update_xbox_names(
                tg_id, gamertag=snapshot.gamertag, gamertag_modern=snapshot.gamertag_modern
            )
        # And the picture (#55), from the same response. Only the URL is
        # written here: downloading it belongs to poller/avatars.py, which
        # does that for every platform on one slow cadence — this is the one
        # platform whose URL can only be read with the person's own token,
        # which is why it is written from here at all.
        if snapshot.avatar_url:
            await self._repo.set_account_avatar_url(xuid, snapshot.avatar_url)


async def catch_up_since(repo: Repo, xuid: str, window_hours: int) -> datetime:
    """Where this account's catch-up window starts (#82).

    The newest unlock already stored, which only moves when an achievement
    actually arrives. Deliberately **not** `presence_state.updated_at`: the
    presence poller writes that on every tick whether or not anything
    changed, so a window measured from it is always "since a minute ago" and
    `_played_since` finds no candidate title at all. That is what made
    startup catch-up a silent no-op on every account — the admin panel's own
    refresh had used the right value all along.

    A floor of `window_hours` back, for two different accounts that both
    need one: an account with nothing stored answers `None`, and an account
    idle for a year answers with a year-old date. Either would have
    `_played_since` hand back the whole library, up to `catchup_max_titles`
    achievement requests per account on every pass, to publish nothing —
    nothing older than the window may be announced anyway. What is older
    than that and still missing is backfill's job, not catch-up's.
    """
    floor = utcnow() - timedelta(hours=window_hours)
    stored = parse_iso(await repo.account_latest_unlock(AccountPlatform.XBOX, xuid))
    return max(stored, floor) if stored is not None else floor


def _played_since(
    history: list[TitleHistoryEntry], since: datetime | None
) -> list[TitleHistoryEntry]:
    """Games touched after our last look, most recent first."""
    entries = [(parse_iso(entry.last_played_at), entry) for entry in history]
    fresh = [
        (played, entry)
        for played, entry in entries
        if played is not None and (since is None or played > since)
    ]
    fresh.sort(key=lambda pair: pair[0], reverse=True)
    return [entry for _, entry in fresh]


def _publishable(row: AchievementRow, moment: datetime, played_at: str | None) -> bool:
    """Whether a row catch-up just stored is recent enough to announce.

    A dated row is placed by its own date. A row with no date falls back to
    **when the game was last played**, which is a real timestamp titlehub
    gives us for the title this row came from — not a guess.

    That fallback is the fix (owner report, 2026-09-17). Most achievements
    are dated, Xbox 360's included — 2331 of production's 2982 x360 rows —
    but Microsoft sends a placeholder (`0001-01-01`, or `1753-01-01`) often
    enough to cost the other 651 theirs, and `parse_timestamp` discards it
    rather than record an unlock in the year 1753. The old rule here was
    `unlocked is not None and unlocked >= moment` — "an unknown date is not
    proof of freshness" — which is true of a backfilled row and false of
    this one: everything reaching this function was just inserted, so the bot
    has never seen it before. The result was that an undated achievement
    could never be announced through catch-up at all, on any account, ever.
    Two people finished a session in Gears of War 3 and the log read
    `catch-up for tg_id=…: 10 titles, 0 published`.

    Still a real check, not `True`: the point of the window is that after a
    fortnight of downtime a chat does not want the archive, and a game last
    played a fortnight ago stays silent on exactly that ground.
    """
    unlocked = parse_iso(row.unlocked_at)
    if unlocked is not None:
        return unlocked >= moment
    played = parse_iso(played_at)
    return played is not None and played >= moment
