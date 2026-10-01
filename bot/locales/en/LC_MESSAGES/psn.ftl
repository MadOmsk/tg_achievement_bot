# Connection and access
psn-not-configured = PSN linking isn't set up yet — ask the administrator.
psn-connect-group-redirect = Message me privately — we'll connect PSN there.
psn-private-only = This command works in a DM.
# Several PSN accounts per person (#10).
psn-has-accounts = 🔵 You already have PSN linked: { $names } ({ $count } of { $max }).

    Add another account?
psn-accounts-full = 🔵 { $max } PSN accounts are linked already — that is the maximum.

    To link a different one, unlink one of them first under "PSN accounts".
psn-add-prompt = 🔵 <b>Another PSN account</b> · { $count } of { $max } once linked

    Send the account's Online ID (its PlayStation Network nickname) in one message. Its trophies must be visible to everyone — PS App → Settings → Privacy → "Trophy level and game collection" → "Anyone".
psn-connected-count = ✅ PSN account <b>{ $name }</b> linked — { $count } of { $max }.
psn-add-button = ➕ Add an account
psn-accounts-button = 🔵 PSN accounts ▸
psn-link-prompt = Send me your PSN Online ID — I'll link it.

    ⚠️ Your trophy privacy has to be open, or I can't read them: in the PS App → Settings → Privacy → “Trophy level and game collection” → “Anyone”.
psn-service-token-dead = PSN is unavailable right now — the service login has expired, please tell the administrator.
psn-profile-not-found = I couldn't find that PSN Online ID: { $raw }. Check the spelling and try again.
psn-profile-private = The profile exists, but its trophies are hidden — I can't read them. Open the privacy setting and try again: PS App → Settings → Privacy → “Trophy level and game collection” → “Anyone”.

# Connected and disconnect
psn-connected = PSN connected: { $name }.
psn-disconnect-confirm-button = Yes, disconnect
psn-cancel-button = Cancel
psn-already-disconnected = PSN isn't connected anyway.
psn-disconnect-prompt = Disconnect PSN ({ $name })?
psn-disconnected = PSN disconnected. You can come back any time.

# Relinking a known account (#52) — the trophies are already stored, and the
# ordinary poll tick picks up whatever appeared since last time.
psn-catch-up-started = I know this account already — its trophies are still here. I will pick up what is new on my own.
