# Shared keyboards (bot/handlers/keyboards.py) — buttons and small labels
# used across the connect flow, the panel, and per-chat cards. Split from
# bot.ftl the same way keyboards.py itself is shared code, not owned by any
# one feature (see the module's own docstring).
# Timezone and digest controls
kb-default = default
kb-tz-other = Other ▸
kb-tz-manual = ✏️ Enter manually
kb-tz-skip = Skip
kb-connect-xbox = Connect XBOX
kb-digest-never = never
# Russian says this with a single genitive plural; English needs the real
# one/other split, so the selection lives here rather than in the caller.
kb-digest-from-n =
    { $threshold ->
        [one] from { $threshold } achievement
       *[other] from { $threshold } achievements
    }
kb-rarity-hidden = don't show
kb-rarity-rare = rare only
kb-rarity-all = all of them

# Connection controls
kb-disconnect-confirm = Yes, disconnect
kb-cancel = Cancel
# /panel's own connect buttons (#33) — "Connect X" with a 🎮 icon,
# uniformly for all three; deliberately wordier than the group hub's own
# short platform-name buttons (chat-hub-*-button), and distinct from
# connect_keyboard's own deep-link kb-connect-xbox above.
kb-panel-connect-xbox = 🎮 Connect Xbox
kb-panel-connect-steam = 🎮 Connect Steam
kb-panel-connect-psn = 🎮 Connect PSN
kb-steam-disconnect = 🔕 Disconnect Steam
kb-psn-disconnect = 🔕 Disconnect PSN
kb-xbox-reconnect = 🔄 Connect again

# Panel controls
kb-timezone-row = Timezone: { $offset } ▸
kb-my-chats = 💬 My chats ▸
kb-sync = 🔄 Sync now
kb-profile-visible = Profile visible to others: { $visible } ▸
kb-profile-visible-yes = yes
kb-profile-visible-no = no
kb-profile = 👤 Profile
kb-xbox-disconnect = 🔕 Disconnect XBOX
kb-refresh = Refresh
kb-back = ‹ Back
kb-open = Open
