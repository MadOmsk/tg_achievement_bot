/** Whose new posts a person is told about: friends, everybody followed, nobody. */

export type PresenceInfo = {
  state: string | null;
  title_name?: string | null;
  game_name?: string | null;
  updated_at: string | null;
};

export type ChatRow = {
  chat_id: number;
  title: string | null;
  is_subscribed: boolean;
};

export type PsnAccount = {
  account_id: string;
  online_id: string | null;
  name: string;
  publishes: boolean;
  trophy_count: number;
  platinum_count: number;
  trophy_level: number | null;
  visibility: string;
  achievements_visible: boolean | null;
  profile_url: string | null;
};

export type AccountPlatform = "xbox" | "psn" | "steam";

/** A person's nickname (#157): `display` is what everybody sees, `number` the
 * four digits added when the name was taken. */
export type Handle = {
  name: string;
  number: number | null;
  display: string;
  confirmed: boolean;
  /** When the next change is allowed, or null if it is now. */
  next_change_at: string | null;
};

/** One side of a merge (#162): what that account brings. */
export type MergeSide = {
  person_id: number;
  handle: string | null;
  email: string | null;
  telegram: string | null;
  has_telegram: boolean;
  /** platform → its accounts, [{ id, name }] */
  accounts: Record<string, Array<{ id: string; name: string | null }>>;
  follows: number;
  chats: number;
};

type Pick<T> = { keep: T; absorb: T };

/** Two accounts that are one person, and where the person must choose (#162). */
export type MergePreview = {
  keep: MergeSide;
  absorb: MergeSide;
  conflicts: {
    xbox?: Pick<{ id: string; name: string | null }>;
    steam?: Pick<{ id: string; name: string | null }>;
    telegram?: Pick<{ name: string | null; admin: boolean }>;
    email?: Pick<string>;
    psn?: { accounts: Array<{ id: string; name: string | null }>; max: number };
  };
};

export type MergeChoices = Partial<{
  xbox: "keep" | "absorb";
  steam: "keep" | "absorb";
  telegram: "keep" | "absorb";
  email: "keep" | "absorb";
  psn: string[];
}>;

/** The ways a person signs in (#162), as Settings → «Вход» shows them. */
export type LoginsResponse = {
  email: string | null;
  telegram: {
    linked: boolean;
    username: string | null;
    /** Whether it may be taken away now; if not, why (`last_login`, `admin`,
     * `in_telegram`). */
    removable?: boolean;
    blocked?: "last_login" | "admin" | "in_telegram" | null;
  };
  /** A merge waiting for the person's word, e.g. after linking Telegram in the bot. */
  merge_pending?: boolean;
  /** Whether a code can be sent at all (a mail server is set up). */
  email_available: boolean;
};

export type MeResponse = {
  /** The person's own id (#156): what the app names people by. */
  person_id: number;
  /** The app's own notices not yet seen (#164). */
  notifications_unread?: number;
  /** No email yet and not put off: the app asks for one once (owner, 2026-10-05). */
  email_prompt?: boolean;
  /** None for a person who signed in by email and has no Telegram (#162). */
  tg_id: number | null;
  handle: Handle | null;
  /** The person chose a picture in the app instead of the Telegram photo. */
  avatar_custom?: boolean;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  is_superadmin: boolean;
  is_excluded: boolean;
  settings: {
    locale: string;
    tz_offset_min: number | null;
    show_profile_links: boolean;
    show_secrets: boolean;
    /** Which achievements go out, in every chat (#126). */
    rarity_mode: string;
    /** Who sees this person's activity in the app (#157). */
    activity_visible?: "all" | "friends" | "nobody";
    /** Where the app's notices go (#164): pushed to devices, and as a DM. */
    notify_push?: boolean;
    notify_telegram?: boolean;
    /** The kinds of notice push and Telegram each carry (none by default). */
    notify_push_on?: string[];
    notify_telegram_on?: string[];
  };
  xbox: {
    linked: boolean;
    /** The owner's switch for this account's posts (#20). */
    publishes?: boolean;
    gamertag: string | null;
    gamertag_modern: string | null;
    xuid: string | null;
    gamerscore: number | null;
    achievement_count: number;
    completed_games: number;
    day: number;
    week: number;
    month: number;
    token_status: string | null;
    needs_reconnect: boolean;
    profile_url: string | null;
    presence: PresenceInfo | null;
  };
  steam:
    | { linked: false }
    | {
        linked: true;
        publishes?: boolean;
        steam_id: string;
        display_name: string | null;
        secondary_name: string | null;
        achievement_count: number;
        completed_games: number;
        day: number;
        week: number;
        month: number;
        visibility: string;
        achievements_visible: boolean | null;
        profile_url: string;
        presence: PresenceInfo | null;
      };
  psn:
    | { linked: false }
    | {
        linked: true;
        publishes?: boolean;
        account_id: string;
        online_id: string | null;
        secondary_name: string | null;
        trophy_count: number;
        platinum_count: number;
        bronze: number;
        silver: number;
        gold: number;
        day: number;
        week: number;
        month: number;
        trophy_level: number | null;
        visibility: string;
        achievements_visible: boolean | null;
        profile_url: string | null;
        presence: PresenceInfo | null;
        /** Every PSN account the person holds (#10), first linked first. */
        accounts?: PsnAccount[];
        max_accounts?: number;
      };
  chats: ChatRow[];
  publication: { excluded: boolean; chat_titles: string[] };
};

export type UserSettingsPatch = Partial<{
  locale: string;
  tz_offset_min: number | null;
  show_profile_links: boolean;
  show_secrets: boolean;
  rarity_mode: string;
  notify_push: boolean;
  notify_telegram: boolean;
  notify_push_on: string[];
  notify_telegram_on: string[];
}>;

// A chat only says whether a person publishes there (#126): the rarity
// mode is the person's (settings), the digest size the chat admin's.
export type ChatPatchAction = "subscribe" | "unsubscribe" | "forget";

export type ChatPatchBody = {
  action?: ChatPatchAction;
  [key: string]: unknown;
};

/** A member's invite codes (owner, 2026-10-05): unused first, then whom each let in. */
export type InviteItem = {
  code: string;
  created_at: string;
  used_at: string | null;
  used_by: { person_id: number; name: string | null } | null;
};

export type InvitesResponse = {
  /** Where a shared link opens; null to build it from the page's own address. */
  link_base: string | null;
  items: InviteItem[];
};

/** Passkeys (owner, 2026-10-08): one's keys, and whether keys work on this host. */
export type PasskeyItem = {
  id: string;
  name: string | null;
  created_at: string;
  last_used_at: string | null;
};

export type PasskeysResponse = { available: boolean; keys: PasskeyItem[] };
