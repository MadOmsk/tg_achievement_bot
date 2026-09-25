-- A person's own switch, per linked account: announce this account's
-- achievements or not (#20). Every account starts on, as everything did.
ALTER TABLE account_links ADD COLUMN publishes INTEGER NOT NULL DEFAULT 1;
