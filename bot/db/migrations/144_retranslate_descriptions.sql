-- The games' descriptions translated by Haiku 4.5 are dropped, to be made
-- again by Haiku 5.5 (owner, 2026-10-30): `poller/translations.py` walks
-- every game and translates what has no Russian. A store's own Russian
-- (`native`) stays. HowLongToBeat's summaries are English only, so every
-- `summary_ru` is ours. Run again on the other server sharing the games
-- database, it only drops what that one made: pennies, translated again.
UPDATE versions SET description_ru = NULL, description_source = NULL, description_ru_of = NULL
 WHERE description_source = 'llm';
UPDATE hltb_entries SET summary_ru = NULL, summary_ru_of = NULL WHERE summary_ru IS NOT NULL;
