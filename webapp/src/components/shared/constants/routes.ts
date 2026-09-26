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
  AVATAR: (tgId: number) => `/avatar/${tgId}`,
  SETTINGS: "/settings",
  CONNECT_XBOX: "/connect/xbox",
  DISCONNECT_XBOX: "/disconnect/xbox",
  CONNECT_STEAM: "/connect/steam",
  DISCONNECT_STEAM: "/disconnect/steam",
  CONNECT_PSN: "/connect/psn",
  DISCONNECT_PSN: "/disconnect/psn",
  SYNC_XBOX: "/sync/xbox",
  CHAT: (chatId: number) => `/chats/${chatId}`,
} as const;

export const CLUB_ROUTES = {
  FEED: "/feed",
  ONLINE: "/online",
  SUMMARY: "/summary",
  PEOPLE: "/people",
} as const;

export const GAMES_ROUTES = {
  TITLE: (platform: string, titleId: string) =>
    `/${encodeURIComponent(platform)}/${encodeURIComponent(titleId)}`,
} as const;

export const ADMIN_ROUTES = {
  HOME: "",
  KEYS: "/keys",
  KEY: (name: string) => `/keys/${encodeURIComponent(name)}`,
  LIMITS: "/limits",
  DEFAULTS: "/defaults",
  USERS: "/users",
  USER: (tgId: number) => `/users/${tgId}`,
  CHATS: "/chats",
  CHAT: (chatId: number) => `/chats/${chatId}`,
  CHAT_ACTIONS: (chatId: number) => `/chats/${chatId}/actions`,
} as const;

export const HLTB_ROUTES = {
  SEARCH: "",
  RESOLVE: (id: number) => `/${id}`,
} as const;
