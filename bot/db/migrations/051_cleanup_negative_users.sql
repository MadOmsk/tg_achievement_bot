-- Remove stray group/chat rows that accidentally ended up in users (#66).
-- In Telegram, real user IDs are positive (tg_id > 0); groups/supergroups/channels
-- have negative IDs.

DELETE FROM user_settings WHERE tg_id <= 0;

DELETE FROM users WHERE tg_id <= 0;
