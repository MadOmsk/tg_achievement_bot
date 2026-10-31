"""The season pass: the themes each person claimed (131), and the pass's levels
with their codes (133), edited by the super-admin as a draft, a pass a month
(136), and the levels each person reached in a month (134). A `month` of None
reads every month."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from bot.db.repo._sql import HANDLE_SHOWN
from bot.util import utcnow

# What an edit may change on a level.
FIELDS = (
    "kind",
    "palette",
    "tier",
    "title",
    "description",
    "points",
    "image_path",
    "game_id",
    "platform",
)
SEEDED = "pass_seeded"
# The super-admins the environment named at the last start (#232).
_ENV_SUPERADMINS = "env_superadmin_tg_ids"

_TAKEN = (
    "(SELECT COUNT(*) FROM pass_item_codes c WHERE c.item_id = i.item_id"
    " AND c.claimed_at IS NOT NULL)"
    " + (SELECT COUNT(*) FROM pass_claims p WHERE i.kind = 'theme' AND p.palette = i.palette)"
)


def _now() -> str:
    return utcnow().isoformat(timespec="seconds")


def _pending(row: Any) -> dict[str, Any]:
    try:
        return json.loads(row["pending"]) if row["pending"] else {}
    except (TypeError, ValueError):
        return {}


class _PassRepo:
    async def wipe_pass_before(self, month: str, marker: str) -> dict[str, int]:
        """Every theme and prize of the passes before `month` taken away, and
        what each person got of them (TEMPORARY, owner, 2026-10-30; see
        `services/season_reset.py`): the levels and their codes, the themes
        claimed, the levels reached and the seasons' names, all of a month
        before `month`; and `marker` set, in one step. A pass of `month` or
        after, and what was claimed in it, stays."""
        gone: dict[str, int] = {}
        async with self.transaction():
            old = "SELECT item_id FROM pass_items WHERE month IS NULL OR month < ?"
            for table, where in (
                ("pass_item_codes", f"item_id IN ({old})"),
                ("pass_reached", "month < ?"),
                ("pass_claims", "month < ?"),
                ("pass_items", "month IS NULL OR month < ?"),
                ("pass_seasons", "month < ?"),
            ):
                cursor = await self._conn.execute(f"DELETE FROM {table} WHERE {where}", (month,))
                gone[table] = cursor.rowcount or 0
            await self._conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES (?, '1', ?)"
                " ON CONFLICT(key) DO UPDATE SET value = '1', updated_at = excluded.updated_at",
                (marker, _now()),
            )
        return gone

    async def pass_claims(self, person_id: int) -> set[str]:
        cursor = await self._conn.execute(
            "SELECT palette FROM pass_claims WHERE person_id = ?", (person_id,)
        )
        return {row[0] for row in await cursor.fetchall()}

    async def set_pass_claim(self, person_id: int, palette: str, month: str, on: bool) -> None:
        if on:
            await self._conn.execute(
                "INSERT INTO pass_claims (person_id, palette, month, claimed_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                (person_id, palette, month, _now()),
            )
        else:
            await self._conn.execute(
                "DELETE FROM pass_claims WHERE person_id = ? AND palette = ?",
                (person_id, palette),
            )
        await self._conn.commit()

    async def ensure_pass_seeded(
        self, themes: Iterable[tuple[str, str, int]], month: str | None = None
    ) -> None:
        """The first pass's levels, the app's themes, written once — from then
        on every month's pass is the super-admin's to build."""
        if await self.get_app_setting(SEEDED):
            return
        now = _now()
        async with self.transaction():
            await self._conn.executemany(
                "INSERT INTO pass_items (kind, palette, tier, points, state, created_at,"
                " published_at, month) VALUES ('theme', ?, ?, ?, 'live', ?, ?, ?)",
                [(palette, tier, points, now, now, month) for palette, tier, points in themes],
            )
        await self.set_app_setting(SEEDED, "1")

    async def pass_live_items(
        self, person_id: int, month: str | None = None
    ) -> list[dict[str, Any]]:
        """A month's pass as everybody sees it: the published levels, with a
        prize's codes left and the one this person took. A level taken down
        stays for whoever took a code of it, so the code is never lost."""
        cursor = await self._conn.execute(
            "SELECT i.*, COUNT(c.code_id) AS total,"
            " COALESCE(SUM(CASE WHEN c.code_id IS NOT NULL AND c.claimed_at IS NULL THEN 1 ELSE"
            " 0 END), 0) AS left_count,"
            " MAX(CASE WHEN c.person_id = ? THEN c.code END) AS mine"
            " FROM pass_items i LEFT JOIN pass_item_codes c ON c.item_id = i.item_id"
            " WHERE i.state != 'draft' AND (?::text IS NULL OR i.month = ?)"
            " GROUP BY i.item_id"
            " HAVING i.state = 'live' OR MAX(CASE WHEN c.person_id = ? THEN c.code END) IS NOT NULL"
            " ORDER BY i.points, i.item_id",
            (person_id, month, month, person_id),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def pass_months(self, until: str) -> list[str]:
        """The months that have a published pass, up to `until`, the latest first."""
        cursor = await self._conn.execute(
            "SELECT DISTINCT month FROM pass_items"
            " WHERE state != 'draft' AND month IS NOT NULL AND month <= ? ORDER BY month DESC",
            (until,),
        )
        return [row[0] for row in await cursor.fetchall()]

    async def pass_season(self, month: str) -> dict[str, Any]:
        """A month's pass's name and cover as shown, and as the editor has them."""
        cursor = await self._conn.execute(
            "SELECT title, image_path, draft, draft_title, draft_image_path"
            " FROM pass_seasons WHERE month = ?",
            (month,),
        )
        row = await cursor.fetchone()
        title = row["title"] if row else None
        image = row["image_path"] if row else None
        draft = bool(row and row["draft"])
        return {
            "title": title,
            "image_path": image,
            "draft_title": row["draft_title"] if draft else title,
            "draft_image_path": row["draft_image_path"] if draft else image,
            "changed": draft,
        }

    async def _season_draft(self, month: str, field: str, value: str | None) -> str | None:
        """One field of a month's draft set; the draft starts from what is shown.
        Gives back the draft cover it replaced, when one goes unused."""
        season = await self.pass_season(month)
        async with self.transaction():
            await self._conn.execute(
                "INSERT INTO pass_seasons (month, draft, draft_title, draft_image_path)"
                " VALUES (?, 1, ?, ?) ON CONFLICT(month) DO UPDATE SET draft = 1,"
                " draft_title = excluded.draft_title,"
                " draft_image_path = excluded.draft_image_path",
                (month, season["draft_title"], season["draft_image_path"]),
            )
            await self._conn.execute(
                f"UPDATE pass_seasons SET {field} = ? WHERE month = ?", (value, month)
            )
        old = season["draft_image_path"]
        if field == "draft_image_path" and old and old not in (value, season["image_path"]):
            return old
        return None

    async def set_pass_season_title(self, month: str, title: str | None) -> None:
        """A month's pass's name changed, waiting for the month's publish."""
        await self._season_draft(month, "draft_title", title)

    async def set_pass_season_image(self, month: str, path: str | None) -> str | None:
        """A month's pass's cover changed (None takes it off), waiting for the
        month's publish. Gives back a draft picture no longer used, to delete."""
        return await self._season_draft(month, "draft_image_path", path)

    async def pass_month_counts(self, months: list[str]) -> dict[str, dict[str, int]]:
        """How many levels each month's pass has, how many wait for its publish,
        and its name as the editor has it."""
        if not months:
            return {}
        marks = ",".join("?" * len(months))
        cursor = await self._conn.execute(
            "SELECT month, COUNT(*), SUM(CASE WHEN state = 'draft' OR pending IS NOT NULL THEN"
            " 1 ELSE 0 END)"
            f" FROM pass_items WHERE state != 'removed' AND month IN ({marks}) GROUP BY month",
            months,
        )
        counts = {
            row[0]: {"levels": int(row[1]), "dirty": int(row[2] or 0)}
            for row in await cursor.fetchall()
        }
        cursor = await self._conn.execute(
            "SELECT month, draft, CASE WHEN draft = 1 THEN draft_title ELSE title END"
            f" FROM pass_seasons WHERE month IN ({marks})",
            months,
        )
        for row in await cursor.fetchall():
            entry = counts.setdefault(row[0], {"levels": 0, "dirty": 0})
            entry["dirty"] += int(bool(row[1]))
            entry["title"] = row[2]
        return counts

    async def pass_editor_items(self, month: str | None = None) -> list[dict[str, Any]]:
        """A month's levels not taken down, as the editor shows them: a draft
        or waiting changes laid over each, how many have it, and its codes."""
        cursor = await self._conn.execute(
            f"SELECT i.*, {_TAKEN} AS taken FROM pass_items i WHERE i.state != 'removed'"
            " AND (?::text IS NULL OR i.month = ?)"
            " ORDER BY i.points, i.item_id",
            (month, month),
        )
        rows = [dict(row) for row in await cursor.fetchall()]
        for row in rows:
            pending = _pending(row)
            row["remove"] = bool(pending.pop("remove", False))
            codes = pending.pop("codes", None)
            row["changed"] = bool(pending) or codes is not None
            row.update({k: v for k, v in pending.items() if k in FIELDS})
            if codes is None:
                cursor = await self._conn.execute(
                    "SELECT code FROM pass_item_codes WHERE item_id = ? ORDER BY code_id",
                    (row["item_id"],),
                )
                codes = [r[0] for r in await cursor.fetchall()]
            row["codes"] = codes
            del row["pending"]
        return rows

    async def pass_item(self, item_id: int) -> dict[str, Any] | None:
        cursor = await self._conn.execute(
            f"SELECT i.*, {_TAKEN} AS taken FROM pass_items i WHERE i.item_id = ?", (item_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def add_pass_item(
        self,
        fields: dict[str, Any],
        codes: list[str],
        created_by: int | None,
        month: str | None = None,
    ) -> int:
        """A new level of a month's pass, a draft until that pass is published."""
        values = [fields.get(k) for k in FIELDS]
        async with self.transaction():
            cursor = await self._conn.execute(
                "INSERT INTO pass_items (" + ", ".join(FIELDS) + ", month, state, created_by,"
                " created_at) VALUES (" + ", ".join("?" * len(FIELDS)) + ", ?, 'draft', ?, ?)"
                " RETURNING item_id",
                (*values, month, created_by, _now()),
            )
            item_id = int((await cursor.fetchone())[0])
            await self._conn.executemany(
                "INSERT INTO pass_item_codes (item_id, code) VALUES (?, ?)",
                [(item_id, code) for code in codes],
            )
        return item_id

    async def edit_pass_item(
        self, item_id: int, fields: dict[str, Any], codes: list[str] | None
    ) -> None:
        """A draft is changed in place; a published level keeps what it shows
        and waits for the publish with its changes."""
        row = await self.pass_item(item_id)
        if row is None:
            return
        changes = {k: v for k, v in fields.items() if k in FIELDS}
        async with self.transaction():
            if row["state"] == "draft":
                if changes:
                    await self._conn.execute(
                        "UPDATE pass_items SET "
                        + ", ".join(f"{k} = ?" for k in changes)
                        + " WHERE item_id = ?",
                        (*changes.values(), item_id),
                    )
                if codes is not None:
                    await self._replace_codes(item_id, codes)
                return
            pending = _pending(row)
            pending.pop("remove", None)
            pending.update(changes)
            if codes is not None:
                pending["codes"] = codes
            await self._conn.execute(
                "UPDATE pass_items SET pending = ? WHERE item_id = ?",
                (json.dumps(pending, ensure_ascii=False), item_id),
            )

    async def _replace_codes(self, item_id: int, codes: list[str]) -> None:
        await self._conn.execute("DELETE FROM pass_item_codes WHERE item_id = ?", (item_id,))
        await self._conn.executemany(
            "INSERT INTO pass_item_codes (item_id, code) VALUES (?, ?)",
            [(item_id, code) for code in codes],
        )

    async def remove_pass_item(self, item_id: int) -> str | None:
        """A draft goes at once (its picture's path given back, to delete); a
        published level is taken down at the publish."""
        row = await self.pass_item(item_id)
        if row is None:
            return None
        if row["state"] == "draft":
            await self._conn.execute("DELETE FROM pass_items WHERE item_id = ?", (item_id,))
            await self._conn.commit()
            return row["image_path"]
        await self._conn.execute(
            "UPDATE pass_items SET pending = ? WHERE item_id = ?",
            (json.dumps({"remove": True}), item_id),
        )
        await self._conn.commit()
        return None

    async def revert_pass_item(self, item_id: int) -> str | None:
        """A published level's waiting changes dropped; a picture they alone
        held given back, to delete."""
        row = await self.pass_item(item_id)
        if row is None:
            return None
        picture = _pending(row).get("image_path")
        await self._conn.execute(
            "UPDATE pass_items SET pending = NULL WHERE item_id = ?", (item_id,)
        )
        await self._conn.commit()
        return picture if picture != row["image_path"] else None

    async def discard_pass_draft(self, month: str | None = None) -> list[str]:
        """A month's draft levels and waiting changes thrown away; the pictures
        they alone held given back, to delete."""
        cursor = await self._conn.execute(
            "SELECT state, image_path, pending FROM pass_items"
            " WHERE (state = 'draft' OR pending IS NOT NULL) AND (?::text IS NULL OR month = ?)",
            (month, month),
        )
        pictures = []
        for row in await cursor.fetchall():
            if row["state"] == "draft" and row["image_path"]:
                pictures.append(row["image_path"])
            waiting = _pending(row).get("image_path")
            if waiting and waiting != row["image_path"]:
                pictures.append(waiting)
        async with self.transaction():
            await self._conn.execute(
                "DELETE FROM pass_items WHERE state = 'draft' AND (?::text IS NULL OR month = ?)",
                (month, month),
            )
            await self._conn.execute(
                "UPDATE pass_items SET pending = NULL WHERE (?::text IS NULL OR month = ?)",
                (month, month),
            )
            cursor = await self._conn.execute(
                "SELECT image_path, draft_image_path FROM pass_seasons"
                " WHERE draft = 1 AND (?::text IS NULL OR month = ?)",
                (month, month),
            )
            for row in await cursor.fetchall():
                if row["draft_image_path"] and row["draft_image_path"] != row["image_path"]:
                    pictures.append(row["draft_image_path"])
            await self._conn.execute(
                "UPDATE pass_seasons SET draft = 0, draft_title = NULL, draft_image_path = NULL"
                " WHERE (?::text IS NULL OR month = ?)",
                (month, month),
            )
        return pictures

    async def publish_pass(self, month: str | None = None) -> dict[str, Any]:
        """A month's draft made its pass, in one transaction: new levels shown,
        changes laid in, levels taken down. A level somebody has by now is left
        as it is. Gives back what changed, the names of the new levels, and
        the pictures no longer used."""
        added: list[str] = []
        changed = removed = skipped = 0
        old_pictures: list[str] = []
        now = _now()
        async with self.transaction():
            cursor = await self._conn.execute(
                f"SELECT i.*, {_TAKEN} AS taken FROM pass_items i"
                " WHERE (i.state = 'draft' OR i.pending IS NOT NULL)"
                " AND (?::text IS NULL OR i.month = ?)",
                (month, month),
            )
            for row in [dict(r) for r in await cursor.fetchall()]:
                item_id = row["item_id"]
                if row["state"] == "draft":
                    await self._conn.execute(
                        "UPDATE pass_items SET state = 'live', published_at = ? WHERE item_id = ?",
                        (now, item_id),
                    )
                    added.append(row["title"] or row["palette"] or "")
                    continue
                pending = _pending(row)
                if row["taken"]:
                    waiting = pending.get("image_path")
                    if waiting and waiting != row["image_path"]:
                        old_pictures.append(waiting)
                    await self._conn.execute(
                        "UPDATE pass_items SET pending = NULL WHERE item_id = ?", (item_id,)
                    )
                    skipped += 1
                    continue
                if pending.get("remove"):
                    await self._conn.execute(
                        "UPDATE pass_items SET state = 'removed', removed_at = ?, pending = NULL"
                        " WHERE item_id = ?",
                        (now, item_id),
                    )
                    removed += 1
                    continue
                codes = pending.pop("codes", None)
                changes = {k: v for k, v in pending.items() if k in FIELDS}
                if (
                    "image_path" in changes
                    and row["image_path"]
                    and row["image_path"] != changes["image_path"]
                ):
                    old_pictures.append(row["image_path"])
                sets = "".join(f"{k} = ?, " for k in changes)
                await self._conn.execute(
                    "UPDATE pass_items SET " + sets + "pending = NULL WHERE item_id = ?",
                    (*changes.values(), item_id),
                )
                if codes is not None:
                    await self._replace_codes(item_id, codes)
                changed += 1
            # The pass's name and cover waiting with the levels.
            cursor = await self._conn.execute(
                "SELECT image_path, draft_image_path FROM pass_seasons"
                " WHERE draft = 1 AND (?::text IS NULL OR month = ?)",
                (month, month),
            )
            for row in await cursor.fetchall():
                if row["image_path"] and row["image_path"] != row["draft_image_path"]:
                    old_pictures.append(row["image_path"])
            cursor = await self._conn.execute(
                "UPDATE pass_seasons SET title = draft_title, image_path = draft_image_path,"
                " draft = 0, draft_title = NULL, draft_image_path = NULL"
                " WHERE draft = 1 AND (?::text IS NULL OR month = ?)",
                (month, month),
            )
            changed += cursor.rowcount
        return {
            "added": added,
            "changed": changed,
            "removed": removed,
            "skipped": skipped,
            "old_pictures": old_pictures,
        }

    async def claim_pass_code(self, item_id: int, person_id: int) -> str | None:
        """One code of a prize for this person: the one they took before, or
        the next one free. None when none is left. One statement takes it, so
        two people tapping at once never get the same code."""
        async with self.transaction():
            cursor = await self._conn.execute(
                "SELECT code FROM pass_item_codes WHERE item_id = ? AND person_id = ?",
                (item_id, person_id),
            )
            row = await cursor.fetchone()
            if row:
                return row[0]
            await self._conn.execute(
                "UPDATE pass_item_codes SET person_id = ?, claimed_at = ?"
                " WHERE code_id = (SELECT code_id FROM pass_item_codes"
                "   WHERE item_id = ? AND claimed_at IS NULL ORDER BY code_id LIMIT 1)"
                " AND claimed_at IS NULL",
                (person_id, _now(), item_id),
            )
            cursor = await self._conn.execute(
                "SELECT code FROM pass_item_codes WHERE item_id = ? AND person_id = ?",
                (item_id, person_id),
            )
            row = await cursor.fetchone()
        return row[0] if row else None

    async def mark_pass_reached(self, person_id: int, month: str, points: int) -> list[int]:
        """The levels of this month's pass its points reach that were not
        reached before, marked reached now — each told once. A level with
        nothing left to take (a theme one has, a prize one took or nobody
        can) is marked and not told."""
        async with self.transaction():
            cursor = await self._conn.execute(
                "SELECT item_id, (CASE WHEN i.kind = 'theme' THEN EXISTS (SELECT 1 FROM"
                "   pass_claims p WHERE p.person_id = ? AND p.palette = i.palette)"
                "   ELSE EXISTS (SELECT 1 FROM pass_item_codes c WHERE c.item_id = i.item_id"
                "     AND c.person_id = ?)"
                "   OR NOT EXISTS (SELECT 1 FROM pass_item_codes c WHERE c.item_id = i.item_id"
                "     AND c.claimed_at IS NULL) END) AS had"
                " FROM pass_items i WHERE state = 'live' AND month = ? AND points > 0"
                " AND points <= ? AND NOT EXISTS (SELECT 1 FROM pass_reached r"
                "   WHERE r.person_id = ? AND r.item_id = i.item_id AND r.month = ?)"
                " ORDER BY points, item_id",
                (person_id, person_id, month, points, person_id, month),
            )
            rows = await cursor.fetchall()
            fresh = [int(row[0]) for row in rows]
            now = _now()
            await self._conn.executemany(
                "INSERT INTO pass_reached (person_id, item_id, month, reached_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT DO NOTHING",
                [(person_id, item_id, month, now) for item_id in fresh],
            )
        return [int(row[0]) for row in rows if not row[1]]

    async def pass_item_takers(self, item_id: int) -> list[dict[str, Any]]:
        """Who took a prize's codes, the latest first: a nickname and a face
        are no secret, the codes are never read here."""
        cursor = await self._conn.execute(
            "SELECT u.id AS person_id, " + HANDLE_SHOWN + ", c.claimed_at"
            " FROM pass_item_codes c JOIN users u ON u.id = c.person_id"
            " WHERE c.item_id = ? AND c.claimed_at IS NOT NULL"
            " ORDER BY c.claimed_at DESC, c.code_id DESC",
            (item_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def person_role(self, person_id: int) -> str | None:
        """`superadmin`, `admin` or None (services/roles.py)."""
        cursor = await self._conn.execute("SELECT role FROM users WHERE id = ?", (person_id,))
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_person_role(self, person_id: int, role: str | None) -> None:
        await self._conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, person_id))
        await self._conn.commit()

    async def ensure_superadmins(self, tg_ids: Iterable[int]) -> None:
        """The super-admins the environment names are super-admins here too;
        one it named last start and names no more is one no longer (its
        role was the environment's, never given in the app: a named one
        cannot be given or taken one). The names are kept in `app_settings`."""
        ids = sorted(set(tg_ids))
        before = {
            int(t)
            for t in json.loads(await self.get_app_setting(_ENV_SUPERADMINS) or "[]")  # type: ignore[attr-defined]
        }
        async with self.transaction():  # type: ignore[attr-defined]
            dropped = sorted(before - set(ids))
            if dropped:
                marks = ",".join("?" * len(dropped))
                await self._conn.execute(
                    "UPDATE users SET role = NULL"
                    f" WHERE role = 'superadmin' AND tg_id IN ({marks})",
                    dropped,
                )
            if ids:
                marks = ",".join("?" * len(ids))
                await self._conn.execute(
                    f"UPDATE users SET role = 'superadmin' WHERE tg_id IN ({marks})", ids
                )
            await self.set_app_setting(_ENV_SUPERADMINS, json.dumps(ids))  # type: ignore[attr-defined]

    async def pass_month_published(self, month: str) -> bool:
        """Whether a month's pass has a live level: an empty one has not started."""
        cursor = await self._conn.execute(
            "SELECT 1 FROM pass_items WHERE month = ? AND state = 'live' LIMIT 1", (month,)
        )
        return await cursor.fetchone() is not None

    async def mark_pass_seen(self, person_id: int, month: str) -> None:
        await self._conn.execute(
            "INSERT INTO pass_seen (person_id, month, seen_at) VALUES (?, ?, ?)"
            " ON CONFLICT DO NOTHING",
            (person_id, month, _now()),
        )
        await self._conn.commit()

    async def pass_seen_in(self, person_id: int, month: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM pass_seen WHERE person_id = ? AND month = ?", (person_id, month)
        )
        return await cursor.fetchone() is not None

    async def mark_season_notified(self, person_id: int, month: str) -> bool:
        """True for the one call that marks it: the one that tells them."""
        cursor = await self._conn.execute(
            "INSERT INTO season_notified (person_id, month, notified_at) VALUES (?, ?, ?)"
            " ON CONFLICT DO NOTHING",
            (person_id, month, _now()),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def all_person_ids(self) -> list[int]:
        cursor = await self._conn.execute("SELECT id FROM users ORDER BY id")
        return [int(row[0]) for row in await cursor.fetchall()]
