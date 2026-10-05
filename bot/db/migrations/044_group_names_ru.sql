-- Trophy group names in both languages (#61). Sony localizes them — verified
-- live: "CTNS: The Heist" / "Город, который никогда не спит: Ограбление",
-- "New Game+" / "Новая игра+" — while it does *not* localize the game's own
-- title ("Marvel's Spider-Man" either way), which is why there is no
-- per-language title store here and never will be.
--
-- The group name is on the second line of every PSN card (#46), so in a
-- Russian chat that line was the one English thing left on it.
--
-- `name` stays as it is: whatever was stored first, and the fallback for a
-- group that has no localized side. The two new columns are what the render
-- picks from.

ALTER TABLE title_groups ADD COLUMN name_ru TEXT;
ALTER TABLE title_groups ADD COLUMN name_en TEXT;
