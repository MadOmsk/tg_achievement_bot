"""An edition's pictures, as each store gives them (#147; owner, 2026-10-15:
editions have covers of their own, kept with the store's own tag). Network
and database free: each function reads one store's answer.

The shape is the versions' `media`: a role (`cover`, `poster`, `background`)
for the pictures we know how to use, and `images` — every picture with the
tag its store gave it (Xbox's `ImagePurpose`, PSN's `role`, Steam's field
name), so nothing a store said is lost."""

from __future__ import annotations

from typing import Any

from bot.services.stores import psn_store, xbox_catalog

# Which picture is an edition's cover, best first, by the role it was given.
COVER_ORDER = ("cover", "poster", "header", "background")


def xbox(product: dict) -> dict[str, Any]:
    """An Xbox bundle product's pictures."""
    local = (product.get("LocalizedProperties") or [{}])[0]
    media: dict[str, Any] = {
        role: url
        for role, url in xbox_catalog._media(local).items()
        if role in ("cover", "poster", "background")
    }
    images = []
    for image in local.get("Images") or []:
        uri = str(image.get("Uri") or "")
        if uri:
            url = "https:" + uri if uri.startswith("//") else uri
            images.append({"tag": str(image.get("ImagePurpose") or ""), "url": url})
    if images:
        media["images"] = images
    return media


def psn(record: dict) -> dict[str, Any]:
    """A PSN product's pictures (`psn_product._products`' merged record)."""
    media: dict[str, Any] = {}
    images = []
    for item in record.get("media") or []:
        if item.get("type") != "IMAGE" or not item.get("url"):
            continue
        tag = str(item.get("role") or "")
        images.append({"tag": tag, "url": str(item["url"])})
        role = psn_store._IMAGE_ROLES.get(tag)
        if role and role not in media:
            media[role] = str(item["url"])
    if images:
        media["images"] = images
    return media


def steam(package: dict) -> dict[str, Any]:
    """A Steam package's pictures: its header (the capsule a package page
    shows), its small logo and its page's background."""
    images = [
        {"tag": tag, "url": str(package[tag])}
        for tag in ("header_image", "small_logo", "page_image")
        if package.get(tag)
    ]
    media: dict[str, Any] = {}
    if package.get("header_image"):
        media["header"] = str(package["header_image"])
    if package.get("page_image"):
        media["background"] = str(package["page_image"])
    if images:
        media["images"] = images
    return media


def cover_url(media: dict[str, Any] | None) -> str | None:
    """The picture that stands for the edition."""
    for role in COVER_ORDER:
        if (media or {}).get(role):
            return str(media[role])  # type: ignore[index]
    return None
