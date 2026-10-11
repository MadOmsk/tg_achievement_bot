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
  /** Every way in, linked or not, labelled by the server (services/logins.py). */
  logins: Array<{ kind: string; label: string; linked: boolean; value: string | null }>;
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
};

/** One setting of the server's registry (#176), as both admin panels draw it. */
export type AdminSetting = {
  key: string;
  label: string;
  hint: string | null;
  kind: "int" | "float" | "bool" | "choice" | "hour" | "tz";
  value: number | string | boolean;
  min: number | null;
  max: number | null;
  zero_means: "unlimited" | "off" | "no_delay" | null;
  /** The values a pick-one setting takes; empty for a number or a switch. */
  options: Array<{ value: number | string; label: string }>;
};

export type AdminSettingsGroup = { id: string; title: string; items: AdminSetting[] };
export type AdminSettings = { groups: AdminSettingsGroup[] };

/** One super-admin action of a card, from the server's registry (#176). */
export type AdminAction = {
  id: string;
  scope: "user" | "account" | "chat" | "global";
  target: string;
  label: string;
  danger: boolean;
  section: string | null;
  section_title: string | null;
};

export type AdminActionDone = { ok: boolean; text: string | null; gone: boolean };

/** One step of an action: the next confirmation to ask, or what it did. */
export type AdminActionStep = {
  confirm?: { text: string; yes: string; step: number };
  done?: AdminActionDone;
};
