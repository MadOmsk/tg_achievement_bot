-- /delete_last may take any bot message except an achievement notification (#101).
ALTER TABLE bot_messages ADD COLUMN is_achievement INTEGER NOT NULL DEFAULT 0;

-- Every notification already sent is in `publications`, keyed by the message
-- the publisher got back — for a digest album that is only the first photo.
UPDATE bot_messages
SET is_achievement = 1
WHERE EXISTS (
    SELECT 1 FROM publications p
    WHERE p.chat_id = bot_messages.chat_id AND p.message_id = bot_messages.message_id
);

-- The album's other photos were logged in the same loop, so they share the
-- first photo's sent_at and follow it within Telegram's 10-item album cap.
UPDATE bot_messages
SET is_achievement = 1
WHERE is_achievement = 0
  AND EXISTS (
    SELECT 1 FROM bot_messages first
    WHERE first.chat_id = bot_messages.chat_id
      AND first.is_achievement = 1
      AND first.sent_at = bot_messages.sent_at
      AND bot_messages.message_id BETWEEN first.message_id + 1 AND first.message_id + 9
);
