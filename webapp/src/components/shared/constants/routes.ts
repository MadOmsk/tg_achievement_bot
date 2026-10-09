export const API_BASE_ROUTES = {
  MINI: "/api/mini",
  CLUB: "/api/mini/club",
  GAMES: "/api/mini/games",
  ADMIN: "/api/mini/admin",
  HLTB: "/api/mini/hltb",
} as const;

export const USER_ROUTES = {
  ME: "/me",
  DELETE_ME: "/me",
  AVATAR: (personId: number) => `/avatar/p/${personId}`,
  SETTINGS: "/settings",
  HANDLE: "/me/handle",
  AVATAR_ME: "/me/avatar",
  CONFIRM_HANDLE: "/me/handle/confirm",
  CONNECT_XBOX: "/connect/xbox",
  DISCONNECT_XBOX: "/disconnect/xbox",
  CONNECT_STEAM: "/connect/steam",
  DISCONNECT_STEAM: "/disconnect/steam",
  CONNECT_PSN: "/connect/psn",
  DISCONNECT_PSN: "/disconnect/psn",
  SYNC_XBOX: "/sync/xbox",
  CHAT: (chatId: number) => `/chats/${chatId}`,
  ACCOUNT: (platform: string) => `/accounts/${platform}`,
} as const;

export const CLUB_ROUTES = {
  FEED: "/feed",
  NEWS: "/news",
  NEWS_POST: "/news/post",
  ONLINE: "/online",
  SUMMARY: "/summary",
  PEOPLE: "/people",
} as const;

export const GAMES_ROUTES = {
  TITLE: (platform: string, titleId: string) =>
    `/${encodeURIComponent(platform)}/${encodeURIComponent(titleId)}`,
  HLTB: (platform: string, titleId: string) =>
    `/${encodeURIComponent(platform)}/${encodeURIComponent(titleId)}/hltb`,
  GUIDES: (platform: string, titleId: string) =>
    `/${encodeURIComponent(platform)}/${encodeURIComponent(titleId)}/guides`,
  PATCHES: (platform: string, titleId: string) =>
    `/${encodeURIComponent(platform)}/${encodeURIComponent(titleId)}/patches`,
} as const;

export const ADMIN_ROUTES = {
  HOME: "",
  KEYS: "/keys",
  KEY: (name: string) => `/keys/${encodeURIComponent(name)}`,
  SETTINGS: "/settings",
  USERS: "/users",
  /** A person by their own id (#156): somebody who signed in by email has no Telegram id. */
  USER: (personId: number) => `/users/p${personId}`,
  CHATS: "/chats",
  CHAT_SETTINGS: (chatId: number) => `/chats/${chatId}/settings`,
  ACTIONS: "/actions",
} as const;

export const HLTB_ROUTES = {
  SEARCH: "",
  RESOLVE: (id: number) => `/${id}`,
} as const;
