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

function initHeaders(initData: string): HeadersInit {
  return {
    "X-Telegram-Init-Data": initData,
    "Content-Type": "application/json",
  };
}

export function isPreview(): boolean {
  if (typeof window === "undefined") return false;
  const q = new URLSearchParams(window.location.search);
  if (q.has("preview")) return true;
  return Boolean(import.meta.env.DEV) && !window.Telegram?.WebApp?.initData;
}

import { previewResponse } from "./preview";

async function api<T>(
  initData: string,
  path: string,
  init?: RequestInit,
): Promise<T> {
  if (isPreview()) {
    return previewResponse(path, init) as T;
  }
  const response = await fetch(path, {
    ...init,
    headers: {
      ...initHeaders(initData),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    let detail = await response.text();
    try {
      const json = JSON.parse(detail) as { error?: string; message?: string };
      detail = json.error || json.message || detail;
    } catch {
      /* keep text */
    }
    throw new Error(`${response.status}: ${detail}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export function fetchMe(initData: string): Promise<MeResponse> {
  return api(initData, "/api/mini/me");
}

export async function fetchAvatarBlob(
  initData: string,
  tgId: number,
): Promise<Blob | null> {
  if (isPreview()) return null;
  const response = await fetch(`/api/mini/avatar/${tgId}`, {
    headers: { "X-Telegram-Init-Data": initData },
  });
  if (!response.ok) return null;
  return response.blob();
}

export function patchSettings(
  initData: string,
  body: Partial<{
    locale: string;
    tz_offset_min: number | null;
    show_profile_links: boolean;
    show_secrets: boolean;
  }>,
): Promise<MeResponse> {
  return api(initData, "/api/mini/settings", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function connectXbox(
  initData: string,
): Promise<{ authorize_url: string }> {
  return api(initData, "/api/mini/connect/xbox", { method: "POST", body: "{}" });
}

export function disconnectXbox(
  initData: string,
): Promise<{ ok: boolean; revoke_url?: string }> {
  return api(initData, "/api/mini/disconnect/xbox", {
    method: "POST",
    body: "{}",
  });
}

export function connectSteam(
  initData: string,
  identity: string,
): Promise<{ ok: boolean; display_name?: string; error?: string }> {
  return api(initData, "/api/mini/connect/steam", {
    method: "POST",
    body: JSON.stringify({ identity }),
  });
}

export function disconnectSteam(initData: string): Promise<{ ok: boolean }> {
  return api(initData, "/api/mini/disconnect/steam", {
    method: "POST",
    body: "{}",
  });
}

export function connectPsn(
  initData: string,
  onlineId: string,
): Promise<{ ok: boolean; online_id?: string; error?: string }> {
  return api(initData, "/api/mini/connect/psn", {
    method: "POST",
    body: JSON.stringify({ online_id: onlineId }),
  });
}

export function disconnectPsn(initData: string): Promise<{ ok: boolean }> {
  return api(initData, "/api/mini/disconnect/psn", {
    method: "POST",
    body: "{}",
  });
}

export function syncXbox(
  initData: string,
): Promise<{ ok: boolean; titles?: number; published?: number; error?: string }> {
  return api(initData, "/api/mini/sync", { method: "POST", body: "{}" });
}

export function patchChat(
  initData: string,
  chatId: number,
  body: Record<string, unknown>,
): Promise<{ ok: boolean; chat?: ChatRow | null; forgotten?: boolean }> {
  return api(initData, `/api/mini/club?chat_id=${chatId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export type FeedProgress = {
  unlocked: number;
  total: number;
  group?: {
    name: string;
    unlocked: number;
    total: number;
  } | null;
};

export type FeedItem = {
  tg_id: number;
  person: string;
  name: string;
  game: string | null;
  gamerscore: number;
  rarity_percent: number | null;
  platform: string;
  unlocked_at: string | null;
  is_secret: boolean;
  title_id: string;
  achievement_id: string;
  icon_url: string | null;
  game_icon_url: string | null;
  description: string | null;
  trophy_type: string | null;
  tier_badge: string | null;
  progress?: FeedProgress | null;
};

export type OnlineMember = {
  tg_id: number;
  name: string;
  state: string | null;
  platform: string;
  title_name: string | null;
  playing: boolean;
  status: string;
  icon: string;
};

export type SummaryMember = {
  tg_id: number;
  name: string;
  count: number;
  score: number;
  rare: number;
  xbox: number;
  steam: number;
  psn: number;
};

export type SummaryGame = {
  title_id: string;
  platform: string;
  name: string | null;
  count: number;
  score: number;
  icon_url?: string | null;
};

export type PersonPayload = {
  tg_id: number;
  name: string;
  platforms: Array<{
    platform: string;
    name: string | null;
    achievement_count?: number;
    trophy_count?: number;
    completed_games?: number;
    platinum_count?: number;
    bronze?: number;
    silver?: number;
    gold?: number;
    gamerscore?: number;
    trophy_level?: number | null;
  }>;
  today: { count: number; score: number; xbox: number; steam: number; psn: number };
  week: { count: number; xbox: number; steam: number; psn: number };
  month: { count: number; score: number; xbox: number; steam: number; psn: number };
  month_key?: string;
  current_month?: string;
  months?: string[];
  games: Array<{
    name: string | null;
    unlocked: number | null;
    gamerscore: number | null;
    platform: string | null;
  }>;
  feed: FeedItem[];
};

export function fetchFeed(
  initData: string,
  chatId: number,
  opts?: { limit?: number; month?: string },
): Promise<{ items: FeedItem[]; month: string; current_month: string; months: string[] }> {
  const query = new URLSearchParams({ chat_id: String(chatId) });
  if (opts?.limit) query.set("limit", String(opts.limit));
  if (opts?.month) query.set("month", opts.month);
  return api(initData, `/api/mini/club/feed?${query}`);
}

export function fetchOnline(
  initData: string,
  chatId: number,
): Promise<{ members: OnlineMember[] }> {
  return api(initData, `/api/mini/club/online?chat_id=${chatId}`);
}

export function fetchSummary(
  initData: string,
  chatId: number,
  opts?: { month?: string },
): Promise<{
  month_key: string;
  current_month: string;
  month_label: string;
  day: SummaryMember[];
  month: SummaryMember[];
  games: SummaryGame[];
}> {
  const query = new URLSearchParams({ chat_id: String(chatId) });
  if (opts?.month) query.set("month", opts.month);
  return api(initData, `/api/mini/club/summary?${query}`);
}

export function fetchPerson(
  initData: string,
  chatId: number,
  tgId: number,
  opts?: { month?: string },
): Promise<PersonPayload> {
  const query = new URLSearchParams({ chat_id: String(chatId), tg_id: String(tgId) });
  if (opts?.month) query.set("month", opts.month);
  return api(initData, `/api/mini/club/people?${query}`);
}

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

export function fetchAdminHome(initData: string): Promise<AdminHome> {
  return api(initData, "/api/mini/admin");
}

export function fetchAdminKeys(initData: string): Promise<AdminKeys> {
  return api(initData, "/api/mini/admin/keys");
}

export function putAdminKey(
  initData: string,
  name: string,
  value: string,
): Promise<AdminKeys> {
  return api(initData, `/api/mini/admin/keys/${name}`, {
    method: "PUT",
    body: JSON.stringify({ value }),
  });
}

export function deleteAdminKey(initData: string, name: string): Promise<AdminKeys> {
  return api(initData, `/api/mini/admin/keys/${name}`, { method: "DELETE" });
}

export function fetchAdminLimits(initData: string): Promise<{ items: AdminLimit[] }> {
  return api(initData, "/api/mini/admin/limits");
}

export function patchAdminLimit(
  initData: string,
  key: string,
  value: number,
): Promise<{ items: AdminLimit[] }> {
  return api(initData, "/api/mini/admin/limits", {
    method: "PATCH",
    body: JSON.stringify({ key, value }),
  });
}

export function fetchAdminDefaults(initData: string): Promise<AdminDefaults> {
  return api(initData, "/api/mini/admin/defaults");
}

export function patchAdminDefaults(
  initData: string,
  body: Partial<AdminDefaults>,
): Promise<AdminDefaults> {
  return api(initData, "/api/mini/admin/defaults", {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function fetchAdminUsers(
  initData: string,
): Promise<{ users: AdminUserRow[]; chats: Array<{ chat_id: number; title: string | null }> }> {
  return api(initData, "/api/mini/admin/users");
}

export function fetchAdminUser(initData: string, tgId: number): Promise<AdminUserCard> {
  return api(initData, `/api/mini/admin/users/${tgId}`);
}

export function patchAdminUser(
  initData: string,
  tgId: number,
  body: Record<string, unknown>,
): Promise<AdminUserCard> {
  return api(initData, `/api/mini/admin/users/${tgId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function fetchAdminChats(initData: string): Promise<{ chats: AdminChatRow[] }> {
  return api(initData, "/api/mini/admin/chats");
}

export function patchAdminChat(
  initData: string,
  chatId: number,
  body: Record<string, unknown>,
): Promise<AdminChatRow> {
  return api(initData, `/api/mini/admin/chats/${chatId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function postAdminChatAction(
  initData: string,
  chatId: number,
  action: string,
): Promise<{ ok: boolean; deleted?: number; preview?: string | null }> {
  return api(initData, `/api/mini/admin/chats/${chatId}/actions`, {
    method: "POST",
    body: JSON.stringify({ action }),
  });
}

export type HltbHit = {
  hltb_id: number;
  name: string;
  release_year: number | null;
  main_hours: number | null;
  extra_hours: number | null;
  completionist_hours: number | null;
  platforms: string[];
  game_url: string | null;
  image_url: string | null;
  genre: string | null;
  description: string | null;
};

export function searchHltb(initData: string, query: string): Promise<{ results: HltbHit[] }> {
  return api(initData, `/api/mini/hltb?q=${encodeURIComponent(query)}`);
}

export function resolveHltb(initData: string, id: number): Promise<HltbHit> {
  return api(initData, `/api/mini/hltb/${id}`);
}
