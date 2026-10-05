-- Game news (owner, 2026-10-05): every post of a game's developer on Steam is
-- kept, not only its patch notes — the Mini App's «Новости» lists them, the
-- game page's «Обновления» still shows the patches. A post's first picture
-- goes on its card.
ALTER TABLE game_patches ADD COLUMN kind TEXT NOT NULL DEFAULT 'patch'
    CHECK (kind IN ('patch', 'news'));
ALTER TABLE game_patches ADD COLUMN image_url TEXT;
-- Read every app again soon, so the posts dropped before come in.
UPDATE steam_apps SET patches_checked_at = NULL;
