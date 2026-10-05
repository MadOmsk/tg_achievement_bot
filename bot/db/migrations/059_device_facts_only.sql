-- The device an achievement was earned on is a fact or nothing (owner, 2026-09-24).
-- A game's platforms (what it was released on) and a device (what somebody played it
-- on) are different things, and both columns had absorbed guesses.

-- 1. A game's platforms come from Xbox titlehub or PSN's title listing — never from
--    presence. repo.ensure_title_device (removed) and migration 055 wrote presence
--    device codenames there; titlehub refills these on the next history refresh.
UPDATE titles
SET platforms = NULL
WHERE json_valid(platforms)
  AND EXISTS (
      SELECT 1 FROM json_each(titles.platforms) j
      WHERE j.value IN ('Scarlett', 'Durango', 'Lockhart', 'Anaconda', 'WindowsOneCore', 'Web')
  );

-- 2. PSN guessed the first of several platforms when presence had nothing, and a
--    guessed row cannot be told from a real one: start PSN over. Steam has no device.
--    Xbox devices came from presence while the game was played: kept. Where nothing
--    is known the column stays NULL; the version shown is derived from the game's
--    own platforms (#114).
UPDATE seen_achievements SET device = NULL WHERE platform IN ('psn', 'steam');
