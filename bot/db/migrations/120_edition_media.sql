-- An edition's pictures (#147; owner, 2026-10-15): editions have covers of
-- their own. `media` is the versions' shape — roles we use and every picture
-- with the tag its store gave it (`services/edition_media.py`) —, and the
-- cover is kept on disk under data/covers/editions/, as game covers are.
ALTER TABLE editions ADD COLUMN media TEXT;
ALTER TABLE editions ADD COLUMN image_path TEXT;
ALTER TABLE editions ADD COLUMN image_hash TEXT;
ALTER TABLE editions ADD COLUMN image_checked_at TEXT;
