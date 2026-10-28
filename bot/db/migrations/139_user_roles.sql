-- Who may run the app (owner, 2026-10-28): `superadmin` (everything, and
-- gives the roles), `admin` (everything but giving roles), NULL an ordinary
-- person. The super-admins named in SUPERADMIN_TG_IDS are written here on
-- every start (`repo.ensure_superadmins`), so the column is the one answer.
ALTER TABLE users ADD COLUMN role TEXT;
