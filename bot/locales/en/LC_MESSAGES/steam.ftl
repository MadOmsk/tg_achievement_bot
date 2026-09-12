# Connection and profile access
steam-not-configured = Steam linking isn't set up yet — ask the administrator.
steam-connect-group-redirect = Message me privately — we'll connect Steam there.
steam-private-only = This command works in a DM.
steam-already-connected = Steam is already connected: { $name }.
steam-link-prompt = Send me a link to your Steam profile (steamcommunity.com/id/...) or just the vanity name — I'll link it.

    ⚠️ Your game details have to be public, or I can't read achievements: { $privacy_url } → “Game details” → “Public”.
steam-link-confirm-yes = Yes, connect it
steam-link-confirm-no = No
steam-link-confirm-prompt = That looks like a Steam profile. Connect it?
steam-link-declined = Fine, not connecting it.
steam-unresolved-profile = I couldn't find that Steam profile. Send a link to the profile — for example, https://steamcommunity.com/id/gaben.
steam-unresolved-profile-nickname-hint =

    If you sent a nickname — I search by the profile URL, not by the name shown in the client: Steam simply has no way to search by that. You can copy the link in the app or on steamcommunity.com → “Edit Profile”.
steam-profile-private = The profile exists, but its game details are hidden — I can't read achievements. Make them public and try again: { $privacy_url } → “Game details” → “Public”.

# Backfill and disconnect
steam-connected = Steam connected: { $name }.
steam-backfill-started = Reading your Steam achievement history, this may take a couple of minutes…
steam-backfill-failed = I couldn't read back your Steam achievement history. Publishing is off for now — link the account again a little later: /connect_steam.
steam-backfill-done = Done: read back { $count } Steam achievements you'd already unlocked — they won't be posted to the chat.
steam-game-details-private = I connected the profile, but your game details are hidden separately from the profile's overall privacy — achievements can't be read. Make that specific setting public: { $privacy_url } → “Game details” → “Public”, then run /connect_steam again.
steam-disconnect-confirm-button = Yes, disconnect
steam-cancel-button = Cancel
steam-already-disconnected = Steam isn't connected anyway.
steam-disconnect-prompt = Disconnect Steam ({ $name })?
steam-disconnected = Steam disconnected. You can come back any time.

# Relinking an account the bot already knows (#52): its history is already
# stored, so only what appeared since last time needs fetching.
steam-catch-up-started = I know this account already — its achievements are still here. Fetching only what is new.
