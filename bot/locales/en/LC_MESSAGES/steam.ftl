# Connection and profile access
steam-not-configured = Steam linking isn't set up yet — ask the super-admin.
steam-connect-group-redirect = Message me privately — we'll connect Steam there.
steam-private-only = This command works in a DM.
steam-already-connected =
    Steam is linked to <b>{ $name }</b> right now.

    Send a link to another Steam profile in one message and I'll switch to it.
steam-just-unlink = 🔌 Just unlink Steam
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

# Connected and disconnect
steam-connected = Steam connected: { $name }.
steam-disconnect-confirm-button = Yes, disconnect
steam-cancel-button = Cancel
steam-already-disconnected = Steam isn't connected anyway.
steam-disconnect-prompt = Disconnect Steam ({ $name })?
steam-disconnected = Steam disconnected. You can come back any time.

# Relinking an account the bot already knows (#52): its history is already
# stored, so only what appeared since last time needs fetching.
steam-catch-up-started = I know this account already — its achievements are still here. Fetching only what is new.
