-- Whether a store offers a DLC now (#147; owner, 2026-10-12), as a version's
-- `on_sale` says it for the game: 1 available, 0 off sale, NULL unknown (a
-- PSN DLC is a trophy group, no store product).
ALTER TABLE dlcs ADD COLUMN on_sale INTEGER;
