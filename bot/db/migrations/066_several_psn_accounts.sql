-- Up to three PSN accounts per person (#10): the one-active-account-per-
-- platform index keeps holding for Xbox and Steam and lets PSN go. The limit
-- of three lives in code (handlers/psn.py), where it can say so to a person.
DROP INDEX IF EXISTS idx_links_one_active_per_platform;
CREATE UNIQUE INDEX idx_links_one_active_per_platform
    ON account_links(tg_id, platform) WHERE is_active = 1 AND platform <> 'psn';
