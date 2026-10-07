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
  /** Sign-in emails sent, against the app's hourly cap and the mail service's daily one. */
  mail: { hour: number; hour_limit: number; day: number; day_limit: number };
  credentials: AdminCredential[];
};

/** One shared credential, from the server's registry (#176): the app draws
 * whatever it lists, labels and hints included. */
export type AdminCredential = {
  name: string;
  label: string;
  hint: string;
  configured: boolean;
  /** "active" / "invalid" where a health check watches it, else null. */
  status: string | null;
  checked_at: string | null;
};

export type AdminKeys = { keys: AdminCredential[] };

export type AdminLimit = {
  key: string;
  label: string;
  value: number;
  min: number;
  max: number;
  zero_means: "unlimited" | "off" | "no_delay" | null;
};

export type AdminDefaults = {
  rarity_mode: string;
  show_profile_links: boolean;
  rare_threshold_percent: number;
};

export type AdminUserRow = {
  person_id: number;
  /** None for somebody who signed in by email (#162). */
  tg_id: number | null;
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
  person_id: number;
  tg_id: number | null;
  email: string | null;
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
  /** One person's achievements at once that make one digest; 99 = never (#126). */
  digest_threshold: number;
  locale: string;
};
