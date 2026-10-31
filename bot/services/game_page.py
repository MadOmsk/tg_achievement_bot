"""The Mini App's game page (#147, stage 5; owner, 2026-10-25), put together
from what the catalog holds: a game's pictures, its story, where it is sold,
its hours, DLC, editions, series and relations. No network: every piece is
read from the database, so the page opens at once.

Nothing here is worded: names of consoles, kinds and sections are the Mini
App's (`i18n`); this module sends codes and values."""

from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
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
    """A game's pictures from its versions' stores: `poster` portrait (Steam's
    poster of now, Xbox's box art, Steam's capsule, PlayStation's cover), `hero` wide (Xbox's or
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
    # Steam's poster of now first (owner, 2026-10-30: a store's box art may
    # carry print marks, or an old season); its fixed capsule is often the
    # art of launch day, so it comes after the Xbox one.
    poster = (
        first("steam", "poster")
        or first("xbox", "poster")
        or (steam_capsule(steam[0]["product_id"]) if steam else None)
        or first("psn", "cover")
        or (icons[0] if icons else None)
    )
    hero = (
        first("steam", "hero")
        or first("xbox", "background")
        or first("psn", "background")
        or first("steam", "screenshots")
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
        # Our translation of a text long enough to show counts whatever its
        # own length, or it would be asked for again and again.
        if len(ru) >= _MIN_DESCRIPTION or (ru and version.get("description_source") == "llm"):
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


_STORE_ORDER = {"steam": 0, "xbox": 1, "psn": 2}


def _newest_first(versions: list[dict[str, Any]], order: dict[str, int]) -> list[dict[str, Any]]:
    """Versions the latest released first (owner, 2026-10-29: the gallery's
    newest pictures lead — the stores date no single picture, a version's day
    is the nearest date there is), the stores in `order` within a day."""
    by_store = sorted(versions, key=lambda v: order.get(str(v.get("store")), 9))
    dated = sorted(
        (v for v in by_store if v.get("release_date")),
        key=lambda v: str(v["release_date"]),
        reverse=True,
    )
    return dated + [v for v in by_store if not v.get("release_date")]


def screenshots_of(versions: list[dict[str, Any]]) -> list[str]:
    """Pictures of the game being played, the newest release's first (Steam's,
    the widest, first within it), each once."""
    shots: list[str] = []
    for version in _newest_first(versions, _STORE_ORDER):
        if version.get("store") in _STORE_ORDER:
            for shot in _media(version.get("media")).get("screenshots") or []:
                url = https(shot) if isinstance(shot, str) else None
                if url and url not in shots:
                    shots.append(url)
    return shots[:SCREENSHOTS_SHOWN]


def videos_of(versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The trailers the stores keep links to (owner, 2026-10-26: the game
    page's gallery plays them): a file where the store has one (PSN's mp4),
    else its HLS stream, with the picture shown before it plays; each once,
    the newest release's first, Xbox's first within it (they come with a
    poster), then Steam's, then PSN's."""
    videos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for version in _newest_first(versions, {"xbox": 0, "steam": 1, "psn": 2}):
        if version.get("store") in ("xbox", "steam", "psn"):
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


def dlc_store_url(store: str | None, product: str | None) -> str | None:
    """A DLC's own page on its store; none for a PSN trophy group (no product)."""
    if not product:
        return None
    if store == "xbox":
        return f"https://www.xbox.com/games/store/x/{product}"
    if store == "steam":
        return f"https://store.steampowered.com/app/{product}"
    if store == "psn":
        return f"https://store.playstation.com/product/{product}"
    return None


def dlcs_of(dlcs: list[dict[str, Any]], game: str) -> list[dict[str, Any]]:
    """The game's DLC, each once across consoles: its picture, day, kind, its
    HLTB hours, what its store says of it, and where it is sold — one entry a
    console, with its store page. A PlayStation trophy group with no store
    product is a DLC too, named by its group."""
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
                "description": None,
                "stores": [],
                "hltb": hltb_of(dlc) if dlc.get("hltb_id") else None,
            }
        card["image"] = card["image"] or https(dlc.get("image_url"))
        if dlc.get("release_date") and (
            not card["release_date"] or dlc["release_date"] < card["release_date"]
        ):
            card["release_date"] = dlc["release_date"]
        if not card["hours"] and dlc.get("comp_main"):
            card["hours"] = round(dlc["comp_main"] / 3600, 1)
        if not card["hltb"] and dlc.get("hltb_id"):
            card["hltb"] = hltb_of(dlc)
        console = str(dlc.get("console") or "")
        if console and console not in card["consoles"]:
            card["consoles"].append(console)
        if not card["description"]:
            card["description"] = (dlc.get("description_en") or "").strip() or None
        store = dlc.get("store")
        seen = any(s["console"] == console and s["store"] == store for s in card["stores"])
        if console and not seen:
            card["stores"].append(
                {
                    "console": console,
                    "store": store,
                    "url": dlc_store_url(store, dlc.get("store_id")),
                    "on_sale": dlc.get("on_sale"),
                }
            )
    # By the day it came out (owner, 2026-10-26), those with no day last.
    return sorted(cards.values(), key=lambda c: (c["release_date"] or "9999", c["name"]))


def edition_store_url(store: str | None, product: str | None) -> str | None:
    """An edition's own page on its store: Xbox's product, Steam's package,
    PlayStation's product."""
    if not product:
        return None
    if store == "xbox":
        return f"https://www.xbox.com/games/store/x/{product}"
    if store == "steam":
        return f"https://store.steampowered.com/sub/{product}"
    if store == "psn":
        return f"https://store.playstation.com/product/{product}"
    return None


def editions_of(editions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The editions the stores sell, each name once, those with a picture
    first; each with what it holds (the games first) and its stores."""
    shown: dict[str, dict[str, Any]] = {}
    for edition in editions:
        name = str(edition.get("name") or "").strip()
        if not name:
            continue
        media = _media(edition.get("media"))
        cover = https(media.get("cover") or media.get("poster") or media.get("header"))
        key = name.lower()
        store = {
            "store": edition.get("store"),
            "url": edition_store_url(edition.get("store"), edition.get("store_id")),
            "on_sale": edition.get("on_sale"),
        }
        # The store's wide art, mostly with no title on it: the page's head.
        hero = https(media.get("background"))
        if key in shown:
            card = shown[key]
            card["cover"] = card["cover"] or cover
            card["hero"] = card["hero"] or hero
            # One button a store: the same edition sold as two products there
            # (one per console) is one shop to go to.
            if all(s["store"] != store["store"] for s in card["stores"]):
                card["stores"].append(store)
        else:
            card = shown[key] = {
                "name": name,
                "kind": edition.get("kind"),
                "store": edition.get("store"),
                "on_sale": edition.get("on_sale"),
                "cover": cover,
                "hero": hero,
                "stores": [store],
                "items": [],
            }
        for item in edition.get("items") or []:
            item_name = str(item.get("name") or "").strip()
            if item_name and all(i["name"].lower() != item_name.lower() for i in card["items"]):
                card["items"].append({"name": item_name, "kind": item.get("item_kind")})
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


async def games_of_lists(
    repo: Any, lists: list[tuple[str, str]], locale: str
) -> dict[tuple[str, str], dict[str, Any]]:
    """The catalog's game of each achievement list (owner, 2026-10-30: the
    catalog is the one place a game lives, the Mini App shows it from there):
    `{game_id, name, poster, hero}`, the name in the reader's language. A list
    in no game yet is left out — its caller shows the list as before, and the
    list becomes a game when its page is first opened (`adopt_list_as_game`)."""
    games: dict[tuple[str, str], int] = {}
    for key in dict.fromkeys(lists):
        game_id = await repo.game_of_list(*key)
        if game_id is not None:
            games[key] = game_id
    cards = await repo.game_cards(list(set(games.values())))
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for key, game_id in games.items():
        if game_id not in cards:
            continue
        card = card_of(cards[game_id])
        name = (card["name_ru"] if locale == "ru" else None) or card["name"]
        found[key] = {
            "game_id": game_id,
            "name": name,
            "poster": card["poster"],
            "hero": card["hero"],
        }
    return found


async def playing_name(
    repo: Any, platform: str | None, title_id: str | None, locale: str
) -> str | None:
    """The catalog's name of the game somebody is playing: an Xbox or Steam
    presence names the list, PlayStation's a store title (CUSA…/PPSA…), which
    `game_of_list` finds among the versions' store ids."""
    if not platform or not title_id:
        return None
    found = await games_of_lists(repo, [(str(platform), str(title_id))], locale)
    game = found.get((str(platform), str(title_id)))
    return game["name"] if game else None


def game_fields(game: dict[str, Any] | None) -> dict[str, Any]:
    """A list-keyed row's game for its JSON: `game_id`, `game_poster`,
    `game_hero` (None each when the list is in no game yet)."""
    return {
        "game_id": game["game_id"] if game else None,
        "game_poster": game["poster"] if game else None,
        "game_hero": game["hero"] if game else None,
    }


async def list_posters(
    repo: Any, lists: list[tuple[str, str]]
) -> dict[tuple[str, str], str | None]:
    """The poster of the game each achievement list is in."""
    found = await games_of_lists(repo, lists, "en")
    return {key: game["poster"] for key, game in found.items()}


async def list_heroes(repo: Any, lists: list[tuple[str, str]]) -> dict[tuple[str, str], str | None]:
    """The wide art of the game each achievement list is in, for a post with
    no picture of its own (owner, 2026-10-29)."""
    found = await games_of_lists(repo, lists, "en")
    return {key: game["hero"] for key, game in found.items()}


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
        # The modes HLTB keeps times for: it is played together, or against.
        "coop": bool(entry.get("comp_lvl_co")),
        "multi": bool(entry.get("comp_lvl_mp")),
    }


_SEARCH_NOISE = re.compile(r"[^\w]+", re.UNICODE)
# Dots inside a word and apostrophes are part of it: "S.T.A.L.K.E.R." is
# found as "stalker", "Assassin's" as "assassins" (owner, 2026-10-27).
_SEARCH_JOINED = re.compile(r"(?<=\w)[.'’](?=\w)", re.UNICODE)
# Words a name is written with or without (owner, 2026-10-29): «the witcher»
# and «witcher» are one search.
_ARTICLES = frozenset({"the", "a", "an"})
# A sequel is written either way: «Mafia 2» finds «Mafia II».
_ROMAN = {
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
    "x": "10",
}


def search_key(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.casefold().replace("ё", "е"))
    # Accents go («Pokémon» is «pokemon»), Cyrillic «й» keeps its breve.
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch) or ch == "\u0306")
    folded = unicodedata.normalize("NFC", folded).replace("&", " and ")
    words = _SEARCH_NOISE.sub(" ", _SEARCH_JOINED.sub("", folded)).split()
    words = [_ROMAN.get(w, w) for w in words if w not in _ARTICLES] or words
    return " ".join(words)


def _joined(words: list[str], flat: str) -> bool:
    """`flat` is words of the name written together («spiderman»: «spider»
    «man»), the last of them begun by three letters at least."""
    if " " in flat or len(flat) < 4:
        return False
    for i in range(len(words)):
        run = ""
        for word in words[i:]:
            if len(run) >= len(flat):
                break
            rest = flat[len(run) :]
            if rest == word or (rest.startswith(word) and len(rest) > len(word)):
                run += word
                if run == flat:
                    return run != words[i]
                continue
            if word.startswith(rest) and len(rest) >= 3 and run:
                return True
            break
    return False


def _initials(words: list[str], query: str) -> bool:
    """A short query of a name's first letters: «gta» is «Grand Theft Auto»,
    a sequel's number kept («gta 5»)."""
    head = query.split()
    if not 2 <= len(head[0]) <= 5 or len(head) > 2:
        return False
    letters = [w for w in words if not w.isdigit()]
    initials = "".join(w[0] for w in letters[: len(head[0])])
    if initials != head[0] or len(letters) < len(head[0]):
        return False
    return len(head) == 1 or head[1] in words


def _close(word: str, other: str) -> bool:
    """One typo apart: a letter missing, added, changed or two swapped — for
    words long enough that one letter is a slip, not another word."""
    if min(len(word), len(other)) < 4 or abs(len(word) - len(other)) > 1:
        return False
    return SequenceMatcher(None, word, other).ratio() >= (0.8 if len(word) < 7 else 0.85)


def rank_search(names: list[tuple[int, str]], query: str) -> list[tuple[int, int, int]]:
    """The games whose names match a query, as `(game_id, rank, length)`, each
    game by its best name (owner, 2026-10-29: found the way people type):
    0 a name equal to it, 1 one starting with it, 2 one with a word starting
    with it, 3 every word of it starting a word of the name, in any order
    («wild witcher»), 4 one containing it, its spaces and hyphens aside
    («spiderman» is «Spider-Man»), 5 every word of it in the name with one typo
    at most («witchr»), 6 the name's first letters («gta»)."""
    wanted = search_key(query)
    if not wanted:
        return []
    wanted_words = wanted.split()
    wanted_flat = wanted.replace(" ", "")
    best: dict[int, tuple[int, int]] = {}
    for game_id, name in names:
        key = search_key(name)
        if not key:
            continue
        words = key.split()
        if key == wanted:
            rank = 0
        elif key.startswith(wanted):
            rank = 1
        elif f" {wanted}" in f" {key}":
            rank = 2
        elif all(any(w.startswith(q) for w in words) for q in wanted_words):
            rank = 3
        elif wanted in key or _joined(words, wanted_flat):
            rank = 4
        elif all(any(w.startswith(q) or _close(q, w) for w in words) for q in wanted_words):
            rank = 5
        elif _initials(words, wanted):
            rank = 6
        else:
            continue
        score = (rank, len(key))
        if game_id not in best or score < best[game_id]:
            best[game_id] = score
    return [(game, rank, length) for game, (rank, length) in best.items()]
