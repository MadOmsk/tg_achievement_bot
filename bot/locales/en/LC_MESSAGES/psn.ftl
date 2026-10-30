# Connection and access
psn-not-configured = PSN linking isn't set up yet — ask the super-admin.
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
psn-service-token-dead = PSN is unavailable right now — the service login has expired, please tell the super-admin.
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

# A player's own PSN token (#233)
psn-token-title = 🔑 <b>Personal PSN token · { $name }</b>
psn-token-none = The account is read with the <b>shared token</b> now — { $slowdown } times less often, and only while its trophies are open to everyone.
psn-token-gives =
    <b>What a personal token gives</b>
    • trophies — even when they are hidden on PSN;
    • status and game in /online — even when the status is hidden;
    • { $slowdown } times more often: your own token waits in no shared queue;
    • later — play time and per-game stats.
psn-token-safety = 🔒 <b>Important.</b> The token is a key to your whole PlayStation account (purchases, messages, settings). We keep it encrypted, show it to nobody and use it only to read your trophies and status. Remove it here at any time; to revoke it at Sony, change your password or «Sign out of all devices». A purchase PIN and 2FA are a good idea.
psn-token-steps =
    <b>How to get the token</b>
    1. In a normal browser (not in Telegram) open playstation.com and sign in to { $who }.
    2. In the same tab open
    <code>https://ca.account.sony.com/api/v1/ssocookie</code>
    3. There is a line like <code>{"{"}"npsso":"…"{"}"}</code> — copy it whole, or just the 64 characters in quotes.
    4. Tap «✏️ Paste the token» and send it as one message.
psn-token-steps-any-account = the account you want
psn-token-alive =
    Status: ✅ working
    Added: { $since }
    Checked: { $checked }

    The account is read with its own token. If the token stops working, the account goes back to the shared one by itself, and I will tell you.
psn-token-dead =
    Status: ⚠️ not working since { $since }
    Sony stopped accepting it (it expired, the password changed, or all devices were signed out).

    Meanwhile the account is read with the shared token — less often, open trophies only.
psn-token-input =
    ✏️ Send the token of <b>{ $name }</b> as one message.
    I will delete the message with the token right away.
psn-token-input-new =
    ✏️ Send the account token as one message — I will tell the account from it.
    I will delete the message with the token right away.
psn-token-ok = ✅ Token added to <b>{ $name }</b>. The account is read with its own token now: trophies and status, hidden ones too, more often.
psn-token-error-format = ❌ That does not look like a token: 64 letters and digits (or the whole <code>{"{"}"npsso":"…"{"}"}</code> line).
psn-token-error-refused = ❌ Sony refused this token — it is old or was not copied whole. Get a fresh one: sign in at playstation.com and open the link from the steps again.
psn-token-error-mismatch = ❌ This token opens <b>{ $other }</b>, not <b>{ $name }</b>. Not saved. Sign in at playstation.com as { $name } and get the token again.
psn-token-error-unavailable = ❌ Could not reach PlayStation Network — try again in a couple of minutes. Not saved.
psn-token-error-too_soon = ❌ Too many tries — try again in ten minutes or so. Not saved.
psn-token-error-not_linked = ❌ This PSN account is not linked to you any more.
psn-token-error-invalid = ❌ The token did not work.
psn-token-delete-confirm =
    Remove the personal token of <b>{ $name }</b>?
    The account will be read with the shared token again — less often, open trophies only.
psn-token-deleted = Token removed. To revoke it at Sony for good, change your password or «Sign out of all devices».
psn-token-steps-button = 📋 How to get the token
psn-token-paste-button = ✏️ Paste the token
psn-token-renew-button = 🔁 Renew the token
psn-token-replace-button = 🔁 Replace the token
psn-token-delete-button = 🗑 Remove the token
psn-token-delete-yes = 🗑 Yes, remove
psn-token-retry-button = ✏️ Paste again
psn-token-open-button = 🔑 To the token
psn-token-to-psn = ‹ To PlayStation
psn-token-back = ‹ Back
psn-token-cancel = ✖️ Cancel
psn-token-button = 🔑 Token { $mark }
psn-token-own = 🔑 own token
psn-token-shared = shared token, polled less often
psn-add-choice =
    ➕ <b>Link a PSN account</b> · { $count } of { $max }

    <b>By nickname</b> — as before: its trophies must be open to everyone.
    <b>By token</b> — the account is told from the token, trophies may be hidden, polled more often.
psn-add-by-nick = 👤 By nickname
psn-add-by-token = 🔑 By token
psn-link-by-token-button = 🔑 Link by token
psn-token-linked = ✅ Linked <b>PSN: { $name }</b> — by token.
