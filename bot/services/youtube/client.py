"""YouTube Data API v3, the few calls guide channels need — raw httpx, as for
Steam and Anthropic. The key travels in the query, and an httpx error carries
the whole URL in its text: nothing here logs or raises one with it.

Quota: every call below costs 1 unit of the 10 000 a day a key gets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/youtube/v3/"
PAGE_SIZE = 50
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
# A refusal that says nothing about the key itself.
_PASSING_REASONS = {"quotaExceeded", "rateLimitExceeded", "userRateLimitExceeded", "backendError"}


class YouTubeError(Exception):
    """A call that failed — never with the key or the URL in its text."""


@dataclass(frozen=True, slots=True)
class Video:
    video_id: str
    title: str
    description: str
    published_at: str | None


async def _get(api_key: str, path: str, params: dict[str, str | int]) -> dict:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(API_BASE + path, params={**params, "key": api_key})
    except httpx.HTTPError as exc:
        raise YouTubeError(f"{path}: {type(exc).__name__}") from None
    if response.status_code != 200:
        raise YouTubeError(f"{path}: HTTP {response.status_code} {_reason(response)}")
    return response.json()


def _reason(response: httpx.Response) -> str:
    try:
        errors = response.json()["error"]["errors"]
        return str(errors[0].get("reason") or "")
    except (ValueError, KeyError, IndexError, TypeError):
        return ""


async def check_alive(api_key: str) -> bool:
    """Whether the key works: one cheap call. A refused quota or YouTube being
    down is not the key's fault."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(
                API_BASE + "videos",
                params={"part": "id", "id": "dQw4w9WgXcQ", "key": api_key},
            )
    except httpx.HTTPError:
        return True
    if response.status_code == 200:
        return True
    if response.status_code in (400, 401, 403):
        return _reason(response) in _PASSING_REASONS
    return True


async def uploads_playlist(api_key: str, channel_id: str) -> str | None:
    """The playlist holding every video the channel uploaded."""
    data = await _get(api_key, "channels", {"part": "contentDetails", "id": channel_id})
    items = data.get("items") or []
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"].get("uploads")


async def playlist_page(
    api_key: str, playlist_id: str, page_token: str | None = None
) -> tuple[list[Video], str | None]:
    """One page of a playlist, newest first for a channel's uploads, with
    each video's whole description; and the next page's token."""
    params: dict[str, str | int] = {
        "part": "snippet",
        "playlistId": playlist_id,
        "maxResults": PAGE_SIZE,
    }
    if page_token:
        params["pageToken"] = page_token
    data = await _get(api_key, "playlistItems", params)
    videos = []
    for item in data.get("items") or []:
        snippet = item.get("snippet") or {}
        video_id = (snippet.get("resourceId") or {}).get("videoId")
        title = snippet.get("title") or ""
        # A deleted or private video stays in the playlist with no content.
        if not video_id or title in ("Deleted video", "Private video"):
            continue
        videos.append(
            Video(
                video_id=video_id,
                title=title,
                description=snippet.get("description") or "",
                published_at=snippet.get("publishedAt"),
            )
        )
    return videos, data.get("nextPageToken")
