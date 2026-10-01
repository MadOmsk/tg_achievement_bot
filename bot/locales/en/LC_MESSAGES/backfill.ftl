# The status of reading an account's history (handlers/backfill.py): one
# message, redrawn every few seconds, ending as the result (owner, 2026-09-30).
backfill-starting = ⏳ Syncing the { $platform } history…
backfill-progress =
    ⏳ Syncing the { $platform } history…
    { $bar }
    { $detail }
backfill-detail-games = { $done } of { $total } { $total ->
    [one] game
   *[other] games
} done · found { $found }
backfill-detail-steps = Step { $done } of { $total } · found { $found }
backfill-done-games =
    ✅ The { $platform } history is synced: { $found } from { $total } { $total ->
        [one] game
       *[other] games
    }.
    They won't be posted to the chat — only new ones from now on.
backfill-done =
    ✅ The { $platform } history is synced: { $found }.
    They won't be posted to the chat — only new ones from now on.
backfill-private-games = ⚠️ { $count } { $count ->
    [one] game has
   *[other] games have
} private settings — their trophies couldn't be read. Open those games' privacy in the PS App.
backfill-hidden-psn =
    ⚠️ The { $platform } trophies are hidden — the history couldn't be read.
    Open them: PS App → Settings → Privacy → "Trophy level and game collection" → "Anyone".
backfill-steam-private =
    ⚠️ The Steam profile is linked, but its game details are hidden separately from the profile — the achievements can't be read.

    Make exactly those public: { $privacy_url } → "Game details" → "Public".
backfill-failed =
    ⚠️ Couldn't finish reading the { $platform } history.
    Posting is off for now so the chat isn't flooded with old achievements.
backfill-retry = 🔄 Try again
backfill-recheck = 🔄 Check again
backfill-panel = ⚙️ Panel
backfill-gone = This account isn't linked any more.
