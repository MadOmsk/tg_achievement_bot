-- A game's own name in both languages (#61).
--
-- Only PlayStation has one: verified live on the owner's counterexample —
-- "Marvel's Wolverine" comes back as "Marvel: Росомаха" from the Russian
-- client, in the very same once-per-game call the group names ride on. Xbox
-- returns the same title under en-US and ru-RU while localizing the
-- achievement names in that same response ('Combat Recruit' / 'Боевой опыт'),
-- and Steam's `gameName` is identical under `l=english` and `l=russian`.
--
-- The columns are not PSN-specific all the same: if another platform ever
-- starts localizing, it has somewhere to put it. `name` stays the fallback.

ALTER TABLE titles ADD COLUMN name_ru TEXT;
ALTER TABLE titles ADD COLUMN name_en TEXT;
