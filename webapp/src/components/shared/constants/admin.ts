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

export type AdminScreen =
  | { name: "keys" }
  | { name: "limits" }
  | { name: "defaults" }
  | { name: "users" }
  | { name: "user"; tgId: number }
  | { name: "chats" }
  | { name: "chat"; chatId: number };
