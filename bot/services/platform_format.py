"""Which platform a screen names, and how (#79, reworked in #114).

Three different questions, one function each:

* `played_version` — which *version of the game* somebody earned an
  achievement in: the achievement card, the digest, /recent. It is the
  game's own original platform, chosen by the device it ran on: an Xbox 360
  game is 360 even through backward compatibility on a Series, a One-only
  game on a Series is One, a Smart Delivery game is the version of the
  console it ran on, a Play Anywhere game played on PC is PC. The cloud
  runs the console version and gets a ☁.
* `game_platforms_label` — what a game was *released on*: the games lists.
  Here Play Anywhere is a thing (XPA); in `played_version` it never is,
  because nobody plays two platforms at once.
* `device_label` — what somebody is on right now: /online.

What cannot be known is not guessed: a game on several platforms with no
device is named by its family (XBOX, PSN, Steam), and so is anything
unrecognised.

Short names drop "XBOX": a platform logo will precede them one day and
complete the name itself. "XBOX" is always upper-case.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

# Canonical platforms. Raw values come from titlehub (a game's `devices`),
# Xbox presence (codenames), PSN's title listing and PSN presence.
SERIES = "series"
ONE = "one"
PC = "pc"
X360 = "360"
MOBILE = "mobile"
CLOUD = "cloud"
PS5 = "ps5"
PS4 = "ps4"
PS3 = "ps3"
VITA = "vita"
PSPC = "pspc"

_RAW: dict[str, str] = {
    **dict.fromkeys(
        (
            "xboxseries",
            "xboxseriesx",
            "xboxseriess",
            "xboxscarlett",
            "scarlett",
            "anaconda",
            "lockhart",
        ),
        SERIES,
    ),
    **dict.fromkeys(("xboxone", "xboxones", "xboxonex", "durango", "xboxdurango", "scorpio"), ONE),
    **dict.fromkeys(("pc", "win32", "windows", "windowsonecore"), PC),
    **dict.fromkeys(("xbox360", "xbox 360", "x360"), X360),
    **dict.fromkeys(("mobile", "ios", "android", "windowsphone"), MOBILE),
    **dict.fromkeys(("web", "cloud"), CLOUD),
    "ps5": PS5,
    "ps4": PS4,
    "ps3": PS3,
    **dict.fromkeys(("psvita", "ps vita", "vita"), VITA),
    **dict.fromkeys(("pspc", "ps pc"), PSPC),
}

_XBOX = {SERIES, ONE, PC, X360, MOBILE, CLOUD}

# (full, short)
_NAMES: dict[str, tuple[str, str]] = {
    SERIES: ("XBOX Series X|S", "Series X|S"),
    ONE: ("XBOX One", "One"),
    PC: ("XBOX PC", "PC"),
    X360: ("XBOX 360", "360"),
    MOBILE: ("XBOX Mobile", "Mobile"),
    PS5: ("PlayStation 5", "PS5"),
    PS4: ("PlayStation 4", "PS4"),
    PS3: ("PlayStation 3", "PS3"),
    VITA: ("PlayStation Vita", "PS Vita"),
    PSPC: ("PS PC", "PS PC"),
}
CLOUD_MARK = "☁"

FAMILY_XBOX = "XBOX"
FAMILY_PSN = "PSN"
FAMILY_STEAM = "Steam"

# Which version of a game a device runs, most native first (#114). A console
# plays its own generation and every older one it is compatible with; the
# cloud runs Series hardware.
_RUNS: dict[str, tuple[str, ...]] = {
    SERIES: (SERIES, ONE),
    CLOUD: (SERIES, ONE),
    ONE: (ONE,),
    PC: (PC,),
    MOBILE: (MOBILE,),
    PS5: (PS5, PS4),
    PS4: (PS4,),
    PS3: (PS3,),
    VITA: (VITA,),
    PSPC: (PSPC,),
}


def canonical(raw: str | None) -> str | None:
    """A raw platform/device string as one of the canonical platforms above."""
    if not raw:
        return None
    return _RAW.get(raw.strip().lower())


def parse_platforms(platforms_raw: str | Iterable[str] | None) -> set[str]:
    """A game's stored platforms (a JSON list) as canonical platforms;
    anything unrecognised (HoloLens, a typo) is dropped rather than shown."""
    if not platforms_raw:
        return set()
    if isinstance(platforms_raw, str):
        text = platforms_raw.strip()
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            parsed = text.split(",")
        items = parsed if isinstance(parsed, list) else []
    else:
        items = list(platforms_raw)
    return {p for p in (canonical(str(item)) for item in items if item) if p}


def game_platforms_json(devices: Iterable[str] | None, *, is_x360: bool = False) -> str | None:
    """What to store in `titles.platforms` from titlehub's `devices`: an Xbox
    360 game lists the consoles that emulate it too, and is still a 360 game."""
    listed = [str(d) for d in devices or () if d]
    if is_x360 or any(canonical(d) == X360 for d in listed):
        return json.dumps(["Xbox360"])
    return json.dumps(listed) if listed else None


def _family(platform: str | None) -> str | None:
    key = (platform or "").lower()
    if key in {"xbox_modern", "xbox_360", "xbox", "modern", "x360"}:
        return FAMILY_XBOX
    if key == "psn":
        return FAMILY_PSN
    if key == "steam":
        return FAMILY_STEAM
    return None


def _name(kind: str, short: bool) -> str:
    full, brief = _NAMES[kind]
    return brief if short else full


def played_version(
    platforms_raw: str | Iterable[str] | None,
    platform: str | None,
    *,
    device: str | None = None,
    short: bool = False,
) -> str:
    """The version of the game an achievement was earned in (#114)."""
    family = _family(platform)
    if family == FAMILY_STEAM:
        return FAMILY_STEAM
    game = parse_platforms(platforms_raw)
    if (platform or "").lower() in {"xbox_360", "x360"} or X360 in game:
        return _name(X360, short)

    on = canonical(device)
    cloud = on == CLOUD
    if on == MOBILE and MOBILE not in game:
        # A phone plays a console game through the cloud.
        on, cloud = CLOUD, True
    mark = f" {CLOUD_MARK}" if cloud else ""

    if len(game) == 1:
        return _name(next(iter(game)), short) + mark
    if game and on:
        for kind in _RUNS.get(on, ()):
            if kind in game:
                return _name(kind, short) + mark
        return family or ""
    if not game and on:
        # Nothing known about the game: the device's own version.
        native = _RUNS.get(on, (on,))[0]
        return _name(native, short) + mark
    return family or ""


def game_platforms_label(
    platforms_raw: str | Iterable[str] | None,
    platform: str | None,
    *,
    short: bool = False,
) -> str:
    """What a game was released on — the games lists (#114)."""
    family = _family(platform)
    if family == FAMILY_STEAM:
        return FAMILY_STEAM
    game = parse_platforms(platforms_raw)
    if (platform or "").lower() in {"xbox_360", "x360"} or X360 in game:
        return _name(X360, short)

    xbox = game & _XBOX
    if xbox:
        console = xbox & {SERIES, ONE}
        if console and PC in xbox:
            return "XPA" if short else "XBOX Play Anywhere"
        if console == {SERIES, ONE}:
            return "One | Series" if short else "XBOX One | Series"
        for kind in (SERIES, ONE, PC, MOBILE):
            if kind in xbox:
                return _name(kind, short)

    psn = [k for k in (PS3, PS4, PS5, VITA) if k in game]
    if len(psn) == 1:
        return _name(psn[0], short)
    if psn:
        if short:
            return " | ".join("Vita" if k == VITA else _name(k, True) for k in psn)
        return "PlayStation " + " | ".join("Vita" if k == VITA else k[-1] for k in psn)
    if PSPC in game:
        return _name(PSPC, short)
    return family or ""


def device_label(device: str | None, *, short: bool = True) -> str | None:
    """The device somebody is on right now — /online. None when unknown."""
    on = canonical(device)
    if on is None:
        return None
    if on == CLOUD:
        return f"{_name(SERIES, short)} {CLOUD_MARK}"
    return _name(on, short)
