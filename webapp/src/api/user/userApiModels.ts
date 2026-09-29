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

export type MeResponse = {
  tg_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  is_admin: boolean;
  is_excluded: boolean;
  settings: {
    locale: string;
    tz_offset_min: number | null;
    show_profile_links: boolean;
    show_secrets: boolean;
    /** Which achievements go out, in every chat (#126). */
    rarity_mode: string;
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
}>;

// A chat only says whether a person publishes there (#126): the rarity
// mode is the person's (settings), the digest size the chat admin's.
export type ChatPatchAction = "subscribe" | "unsubscribe" | "forget";

export type ChatPatchBody = {
  action?: ChatPatchAction;
  [key: string]: unknown;
};
