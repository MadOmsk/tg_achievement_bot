"""The products a PlayStation concept names — add-ons, editions, demos,
themes — read from their store pages and put with the versions they belong to
(#147; owner, 2026-10-15: add-ons, editions and the rest, for the games we
have). A concept (`psn_store`) lists their ids by category and names none;
`stores/psn_product` reads a product's page. This module decides what to ask
and where an answer goes: an add-on is a DLC of the version of its console
(`CUSA` is the PS4's, `PPSA` the PS5's), a game-category product an edition of
its game; the rest is kept as the page said it.

**A concept with more than `DLC_PAGES_MAX` add-ons** (owner, 2026-10-24: DEAD
OR ALIVE 5 Last Round has a thousand, two seconds each) has only its list
kept: each add-on a DLC by its id, its page read when it is wanted
(`read_one`), and whatever is checked against the game's DLC is checked
against that list — an unread page is neither missing nor due."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bot.db.repo import Repo
from bot.services import edition_media
from bot.services.stores import StoreDlc, edition_kind
from bot.services.stores import psn_product as page

log = logging.getLogger(__name__)
SOURCE = "psn_product"
EDITION_CATEGORIES = ("GAME", "PVU_GAME")
ADD_ON = "ADD_ON"
# Add-ons of one concept past which their pages are not read, only listed.
DLC_PAGES_MAX = 100


@dataclass
class Report:
    asked: int = 0
    read: int = 0
    gone: int = 0
    failed: int = 0
    dlcs: int = 0
    editions: int = 0
    kept_only: int = 0
    listed_only: int = 0
    errors: list[str] = field(default_factory=list)


def console_of_product(product_id: str) -> str | None:
    return "ps5" if "PPSA" in product_id else "ps4" if "CUSA" in product_id else None


async def products_of_concepts(
    repo: Repo, origin: str | None, concepts: set[str] | None = None
) -> list[tuple[str, str, str]]:
    """`(concept id, category, product id)` of every product the stored
    concepts of these versions name, each product once."""
    seen: set[str] = set()
    found: list[tuple[str, str, str]] = []
    for concept_id in sorted(await repo.psn_concept_versions(origin)):
        if concepts is not None and concept_id not in concepts:
            continue
        concept = await repo.payload(f"psn:{concept_id}", "psn_store") or {}
        for group in concept.get("categorizedProducts") or []:
            for product_id in group.get("ids") or []:
                if product_id not in seen:
                    seen.add(product_id)
                    found.append((concept_id, str(group.get("topCategory")), str(product_id)))
    return found


def list_only(products: list[tuple[str, str, str]]) -> set[str]:
    """The concepts whose add-ons are too many to read page by page."""
    count: dict[str, int] = {}
    for concept_id, category, _product in products:
        if category == ADD_ON:
            count[concept_id] = count.get(concept_id, 0) + 1
    return {c for c, n in count.items() if n > DLC_PAGES_MAX}


async def read_pages(
    repo: Repo,
    origin: str | None,
    *,
    limit: int | None = None,
    stop_after: int = 5,
    concepts: set[str] | None = None,
) -> Report:
    """Read the pages not read yet (or due again), keep each as it came."""
    report = Report()
    in_a_row = 0
    products = await products_of_concepts(repo, origin, concepts)
    listed = list_only(products)
    for concept_id, category, product_id in products:
        if category == ADD_ON and concept_id in listed:
            report.listed_only += 1
            continue
        subject = f"psn_product:{product_id}"
        if not await repo.fetch_due(subject, SOURCE):
            continue
        if limit is not None and report.asked >= limit:
            break
        report.asked += 1
        try:
            data = await page.fetch_product(product_id)
        except page.ProductPageGone:
            report.gone += 1
            in_a_row = 0
            await repo.record_fetch(subject, SOURCE, status="not_found")
            continue
        except Exception as exc:  # the site's bad minute, never fatal to the loop
            report.failed += 1
            in_a_row += 1
            report.errors.append(f"{product_id}: {exc!r}")
            await repo.record_fetch(subject, SOURCE, status="error", error=repr(exc))
            if in_a_row >= stop_after:
                break
            continue
        in_a_row = 0
        if data is None:
            report.gone += 1
            await repo.record_fetch(subject, SOURCE, status="not_found")
            continue
        changed = await repo.save_payload(subject, SOURCE, data)
        await repo.record_fetch(subject, SOURCE, status="ok", changed=changed)
        report.read += 1
    return report


async def put_in_place(repo: Repo, origin: str | None, concepts: set[str] | None = None) -> Report:
    """Every kept product page of these concepts (all when None), read into
    the DLC and editions of the versions of its concept; an add-on of a
    concept listed only is a DLC by its id. No request: it can be run again
    at any time."""
    report = Report()
    versions_of = await repo.psn_concept_versions(origin)
    products = await products_of_concepts(repo, origin, concepts)
    listed = list_only(products)
    for concept_id, category, product_id in products:
        versions = versions_of.get(concept_id) or []
        if versions:
            await _place(repo, concept_id in listed, category, product_id, versions, report)
    return report


async def read_one(repo: Repo, product_id: str) -> bool:
    """One product's page read now, wanted (an add-on of a concept listed
    only, opened in the viewer), and put in place. Returns whether it was
    read."""
    subject = f"psn_product:{product_id}"
    try:
        data = await page.fetch_product(product_id)
    except page.ProductPageGone:
        await repo.record_fetch(subject, SOURCE, status="not_found")
        return False
    if data is None:
        await repo.record_fetch(subject, SOURCE, status="not_found")
        return False
    changed = await repo.save_payload(subject, SOURCE, data)
    await repo.record_fetch(subject, SOURCE, status="ok", changed=changed)
    versions_of = await repo.psn_concept_versions(None)
    for concept_id, category, product in await products_of_concepts(repo, None):
        if product == product_id and versions_of.get(concept_id):
            await _place(repo, False, category, product_id, versions_of[concept_id], Report())
    return True


async def _place(
    repo: Repo,
    listed: bool,
    category: str,
    product_id: str,
    versions: list[tuple[int, str]],
    report: Report,
) -> None:
    """One product put with the version of its console."""
    console = console_of_product(product_id)
    version_id = next((v for v, c in versions if c == console), versions[0][0])
    payload = await repo.payload(f"psn_product:{product_id}", SOURCE)
    if not payload:
        if listed and category == ADD_ON:
            # Its page not read: in the game's list by its id, named once read.
            await repo.save_dlc(version_id, StoreDlc(store_id=product_id, kind="dlc"))
            report.dlcs += 1
            report.listed_only += 1
        return
    product = page.parse_product(payload)
    if category == ADD_ON:
        await repo.save_dlc(
            version_id,
            StoreDlc(
                store_id=product_id,
                name=product.name,
                kind="dlc",
                release_date=product.release_date,
                description_en=product.description,
                image_url=product.image_url,
            ),
        )
        report.dlcs += 1
    elif category in EDITION_CATEGORIES:
        edition_id = await repo.save_edition(
            "psn",
            product_id,
            product.name,
            edition_kind(product.name),
            media=edition_media.psn(page._products(payload)),
        )
        await repo.save_edition_item(
            edition_id,
            product_id,
            product.name,
            "game",
            is_primary=True,
            version_id=version_id,
            role="main",
        )
        report.editions += 1
    else:
        report.kept_only += 1
