# /start, /connect_xbox, /disconnect_xbox and the timezone picker
# (bot/handlers/connect.py).
# Connection flow
connect-greeting =
    Hi! I post XBOX achievements to your chat — yours and everyone else's.

    What I do:
    • catch new achievements and announce them in the chat;
    • filter by rarity, if you'd rather not publish everything;
    • keep personal stats and a daily summary.

    Let's start by signing in with Microsoft.
connect-timezone-prompt = 🕐 What's your timezone?
connect-xbox-already-connected = XBOX is already connected. Settings are in /panel.
connect-xbox-already-connected-relogin =
    XBOX is already connected. To sign in again, run /disconnect_xbox first.
connect-xbox-not-connected = XBOX isn't connected anyway.
connect-disconnect-yes = Yes, disconnect
connect-disconnect-cancel = Cancel
connect-disconnect-prompt =
    Disconnect XBOX?

    I'll delete your token and subscriptions. Your achievement history stays — the chat's stats need it, and it keeps old achievements from flooding back into the chat if you sign in again.

    The permission itself stays in your Microsoft account — only you can remove it, here: { $revoke_url }
connect-disconnected =
    Disconnected. You can come back any time — /connect_xbox.

    The permission in your Microsoft account is removed here: { $revoke_url }
connect-relogin-prompt =
    Sign in again — old achievements won't fly into the chat, they're already marked as seen.
connect-optout-done =
    Got it, no more reminders. I kept your achievement history — you can come back any time via /connect_xbox.
connect-timezone-skip-done = Fine, skipped. You can change it in /panel.
connect-timezone-set = Timezone: { $offset }. You can change it in /panel.
connect-timezone-manual-hint =
    Send the offset in a single message, with a sign: for example +3, -5 or +5:30.
connect-timezone-manual-invalid = That doesn't look like a real timezone. { $hint }
connect-login-button-hint =
    Press the button and sign in with your Microsoft account. I never see your password — Microsoft asks for it, not me.
