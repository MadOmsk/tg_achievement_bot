export const ADMIN_KEY_NAMES = ["steam", "psn", "anthropic"] as const;
export type AdminKeyName = (typeof ADMIN_KEY_NAMES)[number];

export const ADMIN_USER_PLATFORMS = ["xbox", "psn", "steam"] as const;
export type AdminUserPlatform = (typeof ADMIN_USER_PLATFORMS)[number];

export const ADMIN_CHAT_ACTIONS = {
  DELETE_LAST: "delete_last",
  WIPE_24H: "wipe_24h",
  WIPE_SYSTEM_24H: "wipe_system_24h",
  WIPE_SYSTEM_ALL: "wipe_system_all",
} as const;

export type AdminChatAction =
  (typeof ADMIN_CHAT_ACTIONS)[keyof typeof ADMIN_CHAT_ACTIONS];

/** The admin sub-screens' names — never re-typed as string literals. */
export const ADMIN_SCREENS = {
  KEYS: "keys",
  LIMITS: "limits",
  DEFAULTS: "defaults",
  USERS: "users",
  USER: "user",
  CHATS: "chats",
  CHAT: "chat",
} as const;

const A = ADMIN_SCREENS;

export type AdminScreen =
  | { name: typeof A.KEYS }
  | { name: typeof A.LIMITS }
  | { name: typeof A.DEFAULTS }
  | { name: typeof A.USERS }
  | { name: typeof A.USER; tgId: number }
  | { name: typeof A.CHATS }
  | { name: typeof A.CHAT; chatId: number };
