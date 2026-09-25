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
  rarity_mode: string | null;
  digest_threshold: number | null;
};

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
  };
  xbox: {
    linked: boolean;
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
      };
  chats: ChatRow[];
  publication: { excluded: boolean; chat_titles: string[] };
};

export type UserSettingsPatch = Partial<{
  locale: string;
  tz_offset_min: number | null;
  show_profile_links: boolean;
  show_secrets: boolean;
}>;

export type ChatPatchAction =
  | "subscribe"
  | "unsubscribe"
  | "cycle_rarity"
  | "set_rarity"
  | "set_digest"
  | "forget"
  | "settings";

export type ChatPatchBody = {
  action?: ChatPatchAction;
  rarity_mode?: string;
  digest_threshold?: number | null;
  [key: string]: unknown;
};
