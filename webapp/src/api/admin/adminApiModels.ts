export type AdminHome = {
  users: number;
  excluded: number;
  xbox_linked: number;
  xbox_active: number;
  xbox_broken: number;
  steam_linked: number;
  psn_linked: number;
  chats: number;
  xbox_usage: string;
  steam_usage: string;
  steam_key: string;
  psn_key: string;
  psn_requests: number;
};

export type AdminKeys = {
  steam: boolean;
  psn: boolean;
  anthropic: boolean;
};

export type AdminLimit = {
  key: string;
  label: string;
  value: number;
  min: number;
  max: number;
  zero_means: "unlimited" | "off" | null;
};

export type AdminDefaults = {
  rarity_mode: string;
  show_profile_links: boolean;
};

export type AdminUserRow = {
  tg_id: number;
  name: string;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  is_excluded: boolean;
  last_online_at: string | null;
  today: number;
  month: number;
  xbox: boolean;
  steam: boolean;
  psn: boolean;
  chat_ids: number[];
};

export type AdminUserCard = {
  tg_id: number;
  name: string;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  is_excluded: boolean;
  chats: string[];
  xbox: Record<string, unknown> | null;
  steam: Record<string, unknown> | null;
  psn: Record<string, unknown> | null;
};

export type AdminChatRow = {
  chat_id: number;
  title: string | null;
  is_active: boolean;
  subscribers: number;
  rare_threshold_percent: number;
  daily_summary: boolean;
  daily_summary_time: string;
  tz_offset_min: number;
  min_gamerscore: number;
  flood_limit: number;
  flood_window_minutes: number;
  locale: string;
};
