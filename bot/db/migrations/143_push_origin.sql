-- Which address of the app a browser allowed push on (owner, 2026-10-29): a
-- browser keeps one subscription per address, so every dev tunnel the app
-- was opened on kept getting the same notice. Push goes only to the app's
-- own address now; NULL is one stored before, which still gets it.
ALTER TABLE push_subscriptions ADD COLUMN origin TEXT;
