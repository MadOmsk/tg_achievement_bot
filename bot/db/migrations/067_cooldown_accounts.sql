-- A reset count per account, not only per (person, platform) (#10): with
-- several PSN accounts each one is protected on its own — its own count, its
-- own free re-link — and any of them re-linked from another Telegram account
-- still meets its own cooldown. platform_cooldowns keeps the person's count,
-- which still guards Xbox and Steam (one account per person there).
CREATE TABLE IF NOT EXISTS platform_cooldown_accounts (
    platform       TEXT NOT NULL,
    external_id    TEXT NOT NULL,
    tg_id          INTEGER NOT NULL,
    reset_count    INTEGER NOT NULL DEFAULT 1,
    last_reset_at  TEXT NOT NULL,
    PRIMARY KEY (platform, external_id)
);

INSERT OR IGNORE INTO platform_cooldown_accounts
    (platform, external_id, tg_id, reset_count, last_reset_at)
SELECT platform, external_id, tg_id, reset_count, last_reset_at
FROM platform_cooldowns WHERE external_id IS NOT NULL;
