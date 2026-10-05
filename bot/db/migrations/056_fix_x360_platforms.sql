-- Fix Xbox 360 titles platforms populated with backward-compatibility console devices (#79 follow-up).
-- Microsoft TitleHub returns devices: ["Xbox360", "XboxOne", "XboxSeries"] for backward-compatible
-- Xbox 360 games, which should be normalized to just '["Xbox360"]'.

UPDATE titles
SET platforms = '["Xbox360"]'
WHERE platform IN ('xbox_360', 'x360');
