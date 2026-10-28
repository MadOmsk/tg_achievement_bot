"""The Mini App's game page (#147, stage 5; owner, 2026-10-25), put together
from what the catalog holds: a game's pictures, its story, where it is sold,
its hours, DLC, editions, series and relations. No network: every piece is
read from the database, so the page opens at once.

Nothing here is worded: names of consoles, kinds and sections are the Mini
App's (`i18n`); this module sends codes and values."""

from __future__ import annotations

import json
import re
from typing import Any

from bot.services import game_art, x360_frame
from bot.util import looks_russian

# A game's own versions are shown on its page; a PC of no known store is a
# fallback ("covered") and says nothing a known store does not.
_SHOWN_ROLES = ("version", "enhanced")
SCREENSHOTS_SHOWN = 12
VIDEOS_SHOWN = 6
NEWS_SHOWN = 3
# A version's description is a store's blurb; anything this short is a tagline.
_MIN_DESCRIPTION = 60
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t]+")


def https(url: str | None) -> str | None:
    """The page is https: a plain-http picture is mixed content the browser
    drops (Microsoft's store images still come as http)."""
    if not url:
        return None
    return "https://" + url[len("http://") :] if url.startswith("http://") else url


def _media(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        found = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def steam_capsule(appid: str | int) -> str:
    """Steam's portrait capsule — a fixed address every app with a library
    page has (a game too new for one shows its header instead, client-side)."""
    return (
        f"https://shared.steamstatic.com/store_item_assets/steam/apps/{appid}/library_600x900.jpg"
    )


def list_icons(lists: list[dict[str, Any]]) -> list[str]:
    """The lists' own icons, as a poster stands in from them: a 360 list's
    marked so its console frame is cut off (`x360_frame`)."""
    return [
        x360_frame.mark(row["icon_url"], row.get("platform"))
        for row in lists
        if row.get("icon_url")
    ]


def art_of(versions: list[dict[str, Any]], icons: list[str] | None = None) -> dict[str, str | None]:
    """`store_art` as the Mini App reads it: from our own disk (`game_art`)."""
    return {key: game_art.served(url) for key, url in store_art(versions, icons).items()}


def store_art(
    versions: list[dict[str, Any]], icons: list[str] | None = None
) -> dict[str, str | None]:
    """A game's pictures from its versions' stores: `poster` portrait (Xbox's
    box art, Steam's capsule, PlayStation's cover), `hero` wide (Xbox's or
    PlayStation's hero art, else a Steam screenshot), `header` a wide logo
    banner (Steam). The lists' own icons stand in for a poster."""
    poster = hero = header = None
    by_store: dict[str, list[dict[str, Any]]] = {}
    for version in versions:
        by_store.setdefault(str(version.get("store")), []).append(version)

    # A 360 game's backward-compatible product: its store poster is framed
    # like the list's box art (`x360_frame`), whichever console reads it.
    x360 = {str(v.get("product_id")) for v in by_store.get("xbox", []) if v.get("console") == "360"}

    def first(store: str, key: str) -> str | None:
        for version in by_store.get(store, []):
            value = _media(version.get("media")).get(key)
            if isinstance(value, list) and value and isinstance(value[0], str):
                value = value[0]
            if isinstance(value, str) and value:
                if str(version.get("product_id")) in x360 and key == "poster":
                    return x360_frame.mark(https(value), "xbox_360")
                return value
        return None

    steam = by_store.get("steam", [])
    poster = (
        first("xbox", "poster")
        or (steam_capsule(steam[0]["product_id"]) if steam else None)
        or first("psn", "cover")
        or (icons[0] if icons else None)
    )
    hero = (
        first("xbox", "background") or first("psn", "background") or first("steam", "screenshots")
    )
    header = first("steam", "cover")
    return {"poster": https(poster), "hero": https(hero or header), "header": https(header)}


def store_url(version: dict[str, Any]) -> str | None:
    """A version's own page on its store; none for a stand-in (never a search:
    a name finds other games)."""
    if version.get("stand_in"):
        return None
    store, product = version.get("store"), str(version.get("product_id") or "")
    if store == "xbox":
        return f"https://www.xbox.com/games/store/x/{product}"
    if store == "steam":
        return f"https://store.steampowered.com/app/{product}"
    if store == "psn":
        return f"https://store.playstation.com/concept/{product}"
    return None


def _plain(text: str | None) -> str:
    if not text:
        return ""
    text = _TAG.sub("", text).replace("\r", "")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _version_russian(version: dict[str, Any]) -> str:
    """A version's Russian description, as far as it can be trusted (#230,
    the achievements' rule): the store's own, Cyrillic and not its English
    handed back; or our translation of the English it now has."""
    ru = _plain(version.get("description_ru"))
    if not ru or not looks_russian(ru):
        return ""
    source = version.get("description_source")
    if source == "native":
        return ru
    if source == "llm":
        return (
            ru
            if version.get("description_ru_of") == text_hash(version.get("description_en"))
            else ""
        )
    en = _plain(version.get("description_en"))
    return "" if ru == en else ru


def text_hash(text: str | None) -> str | None:
    """What a translation is of (`hltb_page.summary_hash`, one rule)."""
    from bot.services.stores.hltb_page import summary_hash

    return summary_hash(text)


def _texts(
    versions: list[dict[str, Any]], hltb: dict[str, Any] | None
) -> tuple[list[str], list[tuple[str, str, int]]]:
    """Russian texts, and English ones with where each came from."""
    russian: list[str] = []
    english: list[tuple[str, str, int]] = []
    for version in versions:
        ru = _version_russian(version)
        en = _plain(version.get("description_en"))
        if len(ru) >= _MIN_DESCRIPTION:
            russian.append(ru)
        if len(en) >= _MIN_DESCRIPTION:
            english.append((en, "version", int(version["version_id"])))
    if hltb:
        # A translation of another English summary is stale (`summary_ru_of`).
        of = hltb.get("summary_ru_of")
        if hltb.get("summary_ru") and of in (None, text_hash(hltb.get("summary_en"))):
            russian.append(_plain(hltb["summary_ru"]))
        if hltb.get("summary_en") and hltb.get("hltb_id") is not None:
            english.append((_plain(hltb["summary_en"]), "hltb", int(hltb["hltb_id"])))
    russian.sort(key=len, reverse=True)
    english.sort(key=lambda e: len(e[0]), reverse=True)
    return russian, english


def to_translate(
    versions: list[dict[str, Any]], hltb: dict[str, Any] | None
) -> tuple[str, int, str] | None:
    """The English description a Russian reader is shown for want of a
    Russian one — `(kind, id, raw English)`, kind `version` or `hltb` —, to
    be translated once (#230); None when a Russian one exists."""
    russian, english = _texts(versions, hltb)
    if russian or not english:
        return None
    _, kind, key = english[0]
    if kind == "hltb":
        return kind, key, str(hltb["summary_en"]) if hltb else ""
    raw = next(v["description_en"] for v in versions if int(v["version_id"]) == key)
    return kind, key, str(raw)


def description_of(
    versions: list[dict[str, Any]], hltb: dict[str, Any] | None, locale: str
) -> dict[str, str] | None:
    """The game's story in the reader's language when any source has it: a
    store's own text (the longest), else HowLongToBeat's summary; the other
    language when that is all there is."""
    russian, found = _texts(versions, hltb)
    english = [text for text, _, _ in found]
    order = (russian, english) if locale == "ru" else (english, russian)
    for texts, lang in zip(order, ("ru", "en") if locale == "ru" else ("en", "ru"), strict=True):
        if texts:
            return {"text": texts[0], "lang": lang}
    return None


def genres_of(versions: list[dict[str, Any]], hltb: dict[str, Any] | None) -> list[str]:
    """HowLongToBeat's genres (one vocabulary for every platform), else the
    stores'; each once."""
    found: list[str] = []
    if hltb and hltb.get("genres"):
        found = [g.strip() for g in str(hltb["genres"]).split(",") if g.strip()]
    if not found:
        for version in versions:
            try:
                found += [
                    g for g in json.loads(version.get("genres") or "[]") if isinstance(g, str)
                ]
            except (TypeError, ValueError):
                continue
    seen: set[str] = set()
    return [g for g in found if not (g.lower() in seen or seen.add(g.lower()))]


def platforms_of(versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Where the game is played: one row per console (a PC per store), its
    earliest day, whether it is sold, its store page and its achievement
    list. Demos, tools and a PC of no known store stay off."""
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for version in versions:
        if version.get("role") not in _SHOWN_ROLES:
            continue
        console = str(version.get("console") or "")
        store = str(version.get("store") or "")
        if store == "unknown":
            continue
        key = (store if console == "pc" else "", console)
        row = rows.get(key)
        url = store_url(version)
        day = version.get("release_date")
        listed = (
            {"platform": version["platform"], "title_id": str(version["title_id"])}
            if version.get("platform") and version.get("title_id")
            else None
        )
        if row is None:
            rows[key] = {
                "console": console,
                "store": store,
                "release_date": day,
                "on_sale": version.get("on_sale"),
                "url": url,
                "list": listed,
                "enhanced": version.get("role") == "enhanced",
            }
            continue
        if day and (not row["release_date"] or day < row["release_date"]):
            row["release_date"] = day
        if version.get("on_sale") == 1 or row["on_sale"] is None:
            row["on_sale"] = version.get("on_sale")
        row["url"] = row["url"] or url
        row["list"] = row["list"] or listed
    order = ("series", "one", "360", "pc", "ps5", "ps4", "ps3", "vita", "steam")
    return sorted(
        rows.values(),
        key=lambda r: (order.index(r["console"]) if r["console"] in order else 99, r["store"]),
    )


def screenshots_of(versions: list[dict[str, Any]]) -> list[str]:
    """Pictures of the game being played, Steam's (the widest) first, each once."""
    shots: list[str] = []
    for store in ("steam", "xbox", "psn"):
        for version in versions:
            if version.get("store") != store:
                continue
            for shot in _media(version.get("media")).get("screenshots") or []:
                url = https(shot) if isinstance(shot, str) else None
                if url and url not in shots:
                    shots.append(url)
    return shots[:SCREENSHOTS_SHOWN]


def videos_of(versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The trailers the stores keep links to (owner, 2026-10-26: the game
    page's gallery plays them): a file where the store has one (PSN's mp4),
    else its HLS stream, with the picture shown before it plays; each once,
    Xbox's first (they come with a poster), then Steam's, then PSN's."""
    videos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for store in ("xbox", "steam", "psn"):
        for version in versions:
            if version.get("store") != store:
                continue
            for raw in _media(version.get("media")).get("videos") or []:
                if not isinstance(raw, dict):
                    continue
                url = https(raw.get("url"))
                if not url or url in seen:
                    continue
                seen.add(url)
                hls = https(raw.get("hls")) or (url if ".m3u8" in url else None)
                mp4 = url if ".mp4" in url.split("?")[0] else None
                if not (hls or mp4):
                    continue
                videos.append(
                    {
                        "name": raw.get("name") or None,
                        "mp4": mp4,
                        "hls": hls,
                        "poster": https(raw.get("poster") or raw.get("thumbnail")),
                    }
                )
    return videos[:VIDEOS_SHOWN]


_DLC_NOISE = re.compile(r"[^\w]+", re.UNICODE)


def _dlc_key(name: str, game: str) -> str:
    """One DLC sold on several consoles under slightly different names is one
    card: the game's name taken off the front, punctuation dropped."""
    key = _DLC_NOISE.sub(" ", name.lower()).strip()
    lead = _DLC_NOISE.sub(" ", game.lower()).strip()
    if lead and key.startswith(lead):
        key = key[len(lead) :].strip()
    return key or _DLC_NOISE.sub(" ", name.lower()).strip()


def dlcs_of(dlcs: list[dict[str, Any]], game: str) -> list[dict[str, Any]]:
    """The game's DLC, each once across consoles: its picture, day, kind, its
    HLTB hours and the consoles it is on. A PlayStation trophy group with no
    store product is a DLC too, named by its group."""
    cards: dict[str, dict[str, Any]] = {}
    for dlc in dlcs:
        name = str(dlc.get("name") or "").strip()
        if not name:
            continue
        key = _dlc_key(name, game)
        card = cards.get(key)
        if card is None:
            card = cards[key] = {
                "name": name,
                "image": https(dlc.get("image_url")),
                "release_date": dlc.get("release_date"),
                "kind": dlc.get("kind"),
                "hours": round(dlc["comp_main"] / 3600, 1) if dlc.get("comp_main") else None,
                "consoles": [],
            }
        card["image"] = card["image"] or https(dlc.get("image_url"))
        if dlc.get("release_date") and (
            not card["release_date"] or dlc["release_date"] < card["release_date"]
        ):
            card["release_date"] = dlc["release_date"]
        if not card["hours"] and dlc.get("comp_main"):
            card["hours"] = round(dlc["comp_main"] / 3600, 1)
        console = str(dlc.get("console") or "")
        if console and console not in card["consoles"]:
            card["consoles"].append(console)
    # By the day it came out (owner, 2026-10-26), those with no day last.
    return sorted(cards.values(), key=lambda c: (c["release_date"] or "9999", c["name"]))


def editions_of(editions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The editions the stores sell, each name once, those with a picture
    first."""
    shown: dict[str, dict[str, Any]] = {}
    for edition in editions:
        name = str(edition.get("name") or "").strip()
        if not name:
            continue
        media = _media(edition.get("media"))
        cover = https(media.get("cover") or media.get("poster") or media.get("header"))
        key = name.lower()
        if key in shown:
            shown[key]["cover"] = shown[key]["cover"] or cover
            continue
        shown[key] = {
            "name": name,
            "kind": edition.get("kind"),
            "store": edition.get("store"),
            "on_sale": edition.get("on_sale"),
            "cover": cover,
        }
    # The shortest name first (owner, 2026-10-26): the plain edition leads,
    # the bundles of everything follow.
    return sorted(shown.values(), key=lambda e: (len(e["name"]), e["name"]))


def card_of(card: dict[str, Any]) -> dict[str, Any]:
    """A game as a small card (a series, a relation, a search hit, a favorite)."""
    art = art_of(card.get("media") or [], card.get("icons") or [])
    return {
        "game_id": card["game_id"],
        "name": card.get("name"),
        "name_ru": card.get("name_ru"),
        "year": card.get("year"),
        "poster": art["poster"],
        "hero": art["hero"],
    }


async def list_heroes(repo: Any, lists: list[tuple[str, str]]) -> dict[tuple[str, str], str | None]:
    """The wide art of the game each achievement list is in, for a post with
    no picture of its own (owner, 2026-10-29)."""
    games: dict[tuple[str, str], int] = {}
    for key in dict.fromkeys(lists):
        game_id = await repo.game_of_list(*key)
        if game_id is not None:
            games[key] = game_id
    cards = await repo.game_cards(list(set(games.values())))
    return {key: card_of(cards[g])["hero"] if g in cards else None for key, g in games.items()}


def hltb_of(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    """The hours HowLongToBeat's players took, its score and its age rating."""
    if not entry:
        return None

    def hours(key: str) -> float | None:
        value = entry.get(key)
        return round(value / 3600, 1) if value else None

    return {
        "hltb_id": entry["hltb_id"],
        "main": hours("comp_main"),
        "extra": hours("comp_plus"),
        "completionist": hours("comp_100"),
        "score": entry.get("review_score") or None,
        "rating": entry.get("rating_esrb") or entry.get("rating_pegi") or None,
        "url": f"https://howlongtobeat.com/game/{entry['hltb_id']}",
    }


_SEARCH_NOISE = re.compile(r"[^\w]+", re.UNICODE)
# Dots inside a word and apostrophes are part of it: "S.T.A.L.K.E.R." is
# found as "stalker", "Assassin's" as "assassins" (owner, 2026-10-27).
_SEARCH_JOINED = re.compile(r"(?<=\w)[.'’](?=\w)", re.UNICODE)


def search_key(text: str) -> str:
    folded = _SEARCH_JOINED.sub("", text.casefold().replace("ё", "е"))
    return _SEARCH_NOISE.sub(" ", folded).strip()


def rank_search(names: list[tuple[int, str]], query: str) -> list[tuple[int, int, int]]:
    """The games whose names match a query, as `(game_id, rank, length)`: rank
    0 a name equal to it, 1 one starting with it, 2 one with a word starting
    with it, 3 one containing it — each game by its best name."""
    wanted = search_key(query)
    if not wanted:
        return []
    best: dict[int, tuple[int, int]] = {}
    for game_id, name in names:
        key = search_key(name)
        if not key:
            continue
        if key == wanted:
            rank = 0
        elif key.startswith(wanted):
            rank = 1
        elif f" {wanted}" in f" {key}":
            rank = 2
        elif wanted in key:
            rank = 3
        else:
            continue
        score = (rank, len(key))
        if game_id not in best or score < best[game_id]:
            best[game_id] = score
    return [(game, rank, length) for game, (rank, length) in best.items()]
