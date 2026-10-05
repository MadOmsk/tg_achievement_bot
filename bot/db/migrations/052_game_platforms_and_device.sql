-- Game platforms and earned/playing device separation (#79).
--
-- * `titles.platforms` — available platforms for a game, as reported by the
--   platform API (JSON array of strings, e.g. ["XboxOne", "XboxSeriesX"] or
--   ["PS4", "PSVITA"], or ["PC"]).
-- * `seen_achievements.device` — specific platform/device on which an achievement
--   was earned (NULL for older backfilled achievements).
-- * `presence_state.device` — Xbox device reported in active presence (e.g.
--   XboxSeriesX, XboxOne, WindowsOneCore, Xbox360).
-- * `psn_presence_state.device` — PSN device reported in active presence (e.g.
--   PS5, PS4).

ALTER TABLE titles ADD COLUMN platforms TEXT;

ALTER TABLE seen_achievements ADD COLUMN device TEXT;

ALTER TABLE presence_state ADD COLUMN device TEXT;

ALTER TABLE psn_presence_state ADD COLUMN device TEXT;

-- Seed existing titles where platform is known
UPDATE titles SET platforms = '["Xbox360"]' WHERE platform IN ('xbox_360', 'x360') AND platforms IS NULL;
UPDATE titles SET platforms = '["XboxOne"]' WHERE platform IN ('xbox_modern', 'modern') AND platforms IS NULL;
UPDATE titles SET platforms = '["PC"]' WHERE platform = 'steam' AND platforms IS NULL;
