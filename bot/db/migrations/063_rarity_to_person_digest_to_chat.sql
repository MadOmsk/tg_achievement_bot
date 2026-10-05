-- Which achievements go out is the person's, how many at once make a digest
-- is the chat's (#126). Both were per subscription: somebody in many chats set
-- the same thing in each, and a digest size is about a chat's own pace.

ALTER TABLE user_settings ADD COLUMN rarity_mode TEXT NOT NULL DEFAULT 'all'
    CHECK (rarity_mode IN ('all', 'rare', 'hidden'));

-- The mode a person used most across their subscriptions (on production every
-- person used one mode everywhere); ties go to the more permissive one.
UPDATE user_settings SET rarity_mode = COALESCE((
    SELECT s.rarity_mode FROM subscriptions s
    WHERE s.tg_id = user_settings.tg_id
    GROUP BY s.rarity_mode
    ORDER BY COUNT(*) DESC,
             CASE s.rarity_mode WHEN 'all' THEN 0 WHEN 'rare' THEN 1 ELSE 2 END
    LIMIT 1
), 'all');

ALTER TABLE chat_settings ADD COLUMN digest_threshold INTEGER NOT NULL DEFAULT 3;

-- The size a chat's subscribers used most; ties go to the smaller one.
UPDATE chat_settings SET digest_threshold = COALESCE((
    SELECT s.digest_threshold FROM subscriptions s
    WHERE s.chat_id = chat_settings.chat_id
    GROUP BY s.digest_threshold
    ORDER BY COUNT(*) DESC, s.digest_threshold
    LIMIT 1
), 3);

ALTER TABLE subscriptions DROP COLUMN rarity_mode;
ALTER TABLE subscriptions DROP COLUMN digest_threshold;
