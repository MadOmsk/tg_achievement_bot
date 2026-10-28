-- The platform a prize is for (owner, 2026-10-28): a game's or a code's, as
-- the super-admin writes it (Xbox, PlayStation, Steam, anything); NULL when
-- it is not said.
ALTER TABLE pass_items ADD COLUMN platform TEXT;
