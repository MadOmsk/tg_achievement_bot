"""The products a PlayStation concept names — add-ons, editions, demos,
themes — read from their store pages and put with the versions they belong to
(#147; owner, 2026-10-15: add-ons, editions and the rest, for the games we
have). A concept (`psn_store`) lists their ids by category and names none;
`stores/psn_product` reads a product's page. This module decides what to ask
and where an answer goes: an add-on is a DLC of the version of its console
(`CUSA` is the PS4's, `PPSA` the PS5's), a game-category product an edition of
its game; the rest is kept as the page said it."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bot.db.repo import Repo
from bot.services.stores import StoreDlc, edition_kind
from bot.services.stores import psn_product as page

log = logging.getLogger(__name__)
SOURCE = "psn_product"
EDITION_CATEGORIES = ("GAME", "PVU_GAME")


@dataclass
class Report:
    asked: int = 0
    read: int = 0
    gone: int = 0
    failed: int = 0
    dlcs: int = 0
    editions: int = 0
    kept_only: int = 0
    errors: list[str] = field(default_factory=list)


def console_of_product(product_id: str) -> str | None:
    return "ps5" if "PPSA" in product_id else "ps4" if "CUSA" in product_id else None


async def products_of_concepts(repo: Repo, origin: str | None) -> list[tuple[str, str, str]]:
    """`(concept id, category, product id)` of every product the stored
    concepts of these versions name, each product once."""
    seen: set[str] = set()
    found: list[tuple[str, str, str]] = []
    for concept_id in sorted(await repo.psn_concept_versions(origin)):
        concept = await repo.payload(f"psn:{concept_id}", "psn_store") or {}
        for group in concept.get("categorizedProducts") or []:
            for product_id in group.get("ids") or []:
                if product_id not in seen:
                    seen.add(product_id)
                    found.append((concept_id, str(group.get("topCategory")), str(product_id)))
    return found


async def read_pages(
    repo: Repo, origin: str | None, *, limit: int | None = None, stop_after: int = 5
) -> Report:
    """Read the pages not read yet (or due again), keep each as it came."""
    report = Report()
    in_a_row = 0
    for _concept, _category, product_id in await products_of_concepts(repo, origin):
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


async def put_in_place(repo: Repo, origin: str | None) -> Report:
    """Every kept product page, read into the DLC and editions of the
    versions of its concept. No request: it can be run again at any time."""
    report = Report()
    concepts = await repo.psn_concept_versions(origin)
    for concept_id, category, product_id in await products_of_concepts(repo, origin):
        payload = await repo.payload(f"psn_product:{product_id}", SOURCE)
        versions = concepts.get(concept_id) or []
        if not payload or not versions:
            continue
        product = page.parse_product(payload)
        console = console_of_product(product_id)
        version_id = next((v for v, c in versions if c == console), versions[0][0])
        if category == "ADD_ON":
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
                "psn", product_id, product.name, edition_kind(product.name)
            )
            await repo.save_edition_item(
                edition_id, product_id, product.name, "game", is_primary=True, version_id=version_id
            )
            report.editions += 1
        else:
            report.kept_only += 1
    return report
