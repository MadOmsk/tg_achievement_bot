export const ADMIN_USER_PLATFORMS = ["xbox", "psn", "steam"] as const;
export type AdminUserPlatform = (typeof ADMIN_USER_PLATFORMS)[number];

/** The admin sub-screens' names — never re-typed as string literals. */
export const ADMIN_SCREENS = {
  KEYS: "keys",
  SETTINGS: "settings",
  USERS: "users",
  USER: "user",
  CHATS: "chats",
  CHAT: "chat",
} as const;

const A = ADMIN_SCREENS;

export type AdminScreen =
  | { name: typeof A.KEYS }
  | { name: typeof A.SETTINGS }
  | { name: typeof A.USERS }
  | { name: typeof A.USER; personId: number }
  | { name: typeof A.CHATS }
  | { name: typeof A.CHAT; chatId: number };
