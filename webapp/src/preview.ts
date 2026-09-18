import type {
  AdminChatRow,
  AdminDefaults,
  AdminHome,
  AdminKeys,
  AdminLimit,
  AdminUserCard,
  AdminUserRow,
  FeedItem,
  HltbHit,
  MeResponse,
  OnlineMember,
  PersonPayload,
  SummaryGame,
  SummaryMember,
} from "./api";

const me: MeResponse = {
  tg_id: 1,
  username: "RideTheSun",
  first_name: "RideTheSun",
  last_name: null,
  is_admin: true,
  is_excluded: false,
  settings: { locale: "ru", tz_offset_min: 180, show_profile_links: false, show_secrets: false },
  xbox: {
    linked: true,
    gamertag: "RideTheSun",
    gamertag_modern: "RideTheSun",
    xuid: "xuid",
    gamerscore: 245904,
    achievement_count: 412,
    completed_games: 9,
    week: 4,
    month: 21,
    day: 3,
    token_status: "active",
    needs_reconnect: false,
    profile_url: null,
    presence: {
      state: "Online",
      title_name: "Cupid Parasite",
      game_name: "Cupid Parasite",
      updated_at: new Date().toISOString(),
    },
  },
  steam: { linked: false },
  psn: { linked: false },
  chats: [
    {
      chat_id: -100,
      title: "Тусовка",
      is_subscribed: true,
      rarity_mode: "all",
      digest_threshold: 3,
    },
  ],
  publication: { excluded: false, chat_titles: ["Тусовка"] },
};

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString();

const feedItem = (
  name: string,
  game: string,
  id: string,
  extra: Partial<FeedItem> = {},
): FeedItem => ({
  tg_id: 1,
  person: "RideTheSun",
  name,
  game,
  gamerscore: 50,
  rarity_percent: 4.2,
  platform: "xbox_modern",
  unlocked_at: hoursAgo(1),
  is_secret: false,
  title_id: id,
  achievement_id: `a${id}`,
  icon_url: `https://picsum.photos/seed/${id}/800/640`,
  game_icon_url: `https://picsum.photos/seed/g${id}/200/200`,
  description: "Finish the true route.",
  trophy_type: null,
  tier_badge: null,
  progress: { unlocked: 12, total: 50 },
  ...extra,
});

const person: PersonPayload = {
  tg_id: 1,
  name: "Preview",
  platforms: [
    {
      platform: "xbox",
      name: "GlassHero",
      achievement_count: 412,
      completed_games: 9,
      gamerscore: 12480,
    },
  ],
  today: { count: 3, score: 70, xbox: 3, steam: 0, psn: 0 },
  week: { count: 4, xbox: 4, steam: 0, psn: 0 },
  month: { count: 21, score: 410, xbox: 21, steam: 0, psn: 0 },
  games: [{ name: "Cupid Parasite", unlocked: 8, gamerscore: 180, platform: "xbox_modern" }],
  feed: [feedItem("True Love", "Cupid Parasite", "2")],
};

const online: OnlineMember[] = [
  {
    tg_id: 2,
    name: "Forrogmir",
    state: "Online",
    platform: "xbox",
    title_name: "METAL GEAR SOLID: Peace Walker",
    playing: true,
    status: "играет",
    icon: "🎮",
  },
  {
    tg_id: 3,
    name: "HeCnu",
    state: "Online",
    platform: "xbox",
    title_name: "Dying Light: The Beast",
    playing: true,
    status: "играет",
    icon: "🎮",
  },
  {
    tg_id: 4,
    name: "P1LEDR1V3R",
    state: "Online",
    platform: "xbox",
    title_name: "Yakuza Kiwami 3",
    playing: true,
    status: "играет",
    icon: "🎮",
  },
  {
    tg_id: 5,
    name: "Key",
    state: "Online",
    platform: "steam",
    title_name: "Hades II",
    playing: true,
    status: "играет",
    icon: "🎮",
  },
  {
    tg_id: 6,
    name: "Mira",
    state: "Online",
    platform: "psn",
    title_name: "Astro Bot",
    playing: true,
    status: "играет",
    icon: "🎮",
  },
  {
    tg_id: 7,
    name: "Nova",
    state: "Offline",
    platform: "xbox",
    title_name: null,
    playing: false,
    status: "офлайн",
    icon: "💤",
  },
  {
    tg_id: 8,
    name: "Ash",
    state: "Offline",
    platform: "steam",
    title_name: null,
    playing: false,
    status: "офлайн",
    icon: "💤",
  },
];

const summaryMember = (
  tg_id: number,
  name: string,
  count: number,
  score: number,
  rare = 0,
): SummaryMember => ({
  tg_id,
  name,
  count,
  score,
  rare,
  xbox: count,
  steam: 0,
  psn: 0,
});

const games: SummaryGame[] = [
  { title_id: "2", platform: "xbox_modern", name: "Cupid Parasite", count: 8, score: 180, icon_url: "https://picsum.photos/seed/g2/200/200" },
  { title_id: "3", platform: "xbox_modern", name: "Dying Light: The Beast", count: 5, score: 110, icon_url: "https://picsum.photos/seed/g3/200/200" },
  { title_id: "7", platform: "xbox_modern", name: "Yakuza Kiwami 3", count: 4, score: 80, icon_url: "https://picsum.photos/seed/g7/200/200" },
];

const adminHome: AdminHome = {
  users: 12,
  excluded: 0,
  xbox_linked: 8,
  xbox_active: 7,
  xbox_broken: 1,
  steam_linked: 6,
  psn_linked: 4,
  chats: 2,
  xbox_usage: "12/300 · 5 min",
  steam_usage: "3/100 · 5 min",
  steam_key: "alive",
  psn_key: "alive",
  psn_requests: 40,
};

const keys: AdminKeys = { steam: true, psn: true, anthropic: false };

const limits: AdminLimit[] = [
  { key: "summary_top_limit", label: "summary rows", value: 10, min: 0, max: 50, zero_means: "unlimited" },
];

const defaults: AdminDefaults = { rarity_mode: "all", show_profile_links: false };

const adminUser: AdminUserRow = {
  tg_id: 1,
  name: "Preview",
  username: "preview",
  first_name: "Preview",
  last_name: null,
  is_excluded: false,
  last_online_at: new Date().toISOString(),
  today: 3,
  month: 21,
  xbox: true,
  steam: false,
  psn: false,
  chat_ids: [],
};

const adminCard: AdminUserCard = {
  tg_id: 1,
  name: "Preview",
  username: "preview",
  first_name: "Preview",
  last_name: null,
  is_excluded: false,
  chats: ["Тусовка"],
  xbox: { linked: true, name: "GlassHero", token_status: "active" },
  steam: null,
  psn: null,
};

const adminChat: AdminChatRow = {
  chat_id: -100,
  title: "Тусовка",
  is_active: true,
  subscribers: 8,
  rare_threshold_percent: 10,
  daily_summary: true,
  daily_summary_time: "21:00",
  tz_offset_min: 180,
  min_gamerscore: 0,
  flood_limit: 3,
  flood_window_minutes: 60,
  locale: "ru",
};

const hltb: HltbHit = {
  hltb_id: 1,
  name: "Metro 2033",
  release_year: 2010,
  main_hours: 9.53,
  extra_hours: 12.13,
  completionist_hours: 21.2,
  platforms: ["PC", "Xbox"],
  game_url: "https://howlongtobeat.com/game/1",
  image_url: "https://picsum.photos/seed/metro/800/640",
  genre: "First-Person, Real-Time, Action, Adventure, Shooter, Survival",
  description:
    "Metro 2033 is a single player first-person shooter (FPS) that incorporates role-playing game (RPG) elements. Based on the novel of the same name.",
};

export const previewMe = me;

export function previewResponse(path: string, init?: RequestInit): unknown {
  const method = (init?.method ?? "GET").toUpperCase();
  if (path === "/api/mini/me") return me;
  if (path.includes("/feed")) {
    const month = new URL(path, "https://local.invalid").searchParams.get("month");
    const now = new Date();
    const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const previous = `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`;
    const thisMonth = [
        feedItem("Command an elite squad today", "STAR WARS Zero Company", "1", {
          progress: { unlocked: 4, total: 22 },
        }),
        feedItem("True Love", "Cupid Parasite", "2", {
          tg_id: 2,
          person: "Forrogmir",
          rarity_percent: 8.1,
          unlocked_at: hoursAgo(3),
          progress: { unlocked: 18, total: 48 },
        }),
        feedItem("Night Raid", "Dying Light: The Beast", "3", {
          tg_id: 3,
          person: "HeCnu",
          rarity_percent: 12,
          unlocked_at: hoursAgo(5),
          progress: { unlocked: 9, total: 60 },
        }),
        feedItem("Hidden Route", "Cupid Parasite", "4", {
          rarity_percent: 2.1,
          progress: { unlocked: 19, total: 48 },
        }),
        feedItem("Heist Complete", "Marvel's Spider-Man", "psn1", {
          tg_id: 6,
          person: "Mira",
          platform: "psn",
          gamerscore: 0,
          rarity_percent: 6.4,
          trophy_type: "gold",
          tier_badge: "🥇",
          unlocked_at: hoursAgo(6),
          progress: {
            unlocked: 51,
            total: 74,
            group: { name: "Ограбление", unlocked: 3, total: 7 },
          },
        }),
        feedItem("Secret Boss", "Silent Hill", "5", {
          is_secret: true,
          gamerscore: 100,
          rarity_percent: 1.8,
          unlocked_at: hoursAgo(8),
          progress: { unlocked: 11, total: 42 },
        }),
        feedItem("Midnight Walk", "Silent Hill", "6", {
          is_secret: true,
          gamerscore: 15,
          rarity_percent: 22.4,
          unlocked_at: hoursAgo(10),
        }),
        feedItem("Daybreak", "Yakuza Kiwami 3", "7", {
          tg_id: 4,
          person: "P1LEDR1V3R",
          unlocked_at: hoursAgo(14),
          progress: { unlocked: 27, total: 59 },
        }),
        feedItem("First Blood", "Dying Light: The Beast", "8", {
          rarity_percent: 31,
          unlocked_at: hoursAgo(20),
          progress: { unlocked: 10, total: 60 },
        }),
    ];
    const lastMonth = [
      feedItem("Old Wound", "Halo Infinite", "9", {
        rarity_percent: 41,
        unlocked_at: new Date(prev.getFullYear(), prev.getMonth(), 12).toISOString(),
      }),
      feedItem("Quiet Exit", "Cupid Parasite", "10", {
        rarity_percent: 18,
        unlocked_at: new Date(prev.getFullYear(), prev.getMonth(), 8).toISOString(),
      }),
    ];
    const key = month && /^\d{4}-\d{2}$/.test(month) ? month : current;
    const items = key === previous ? lastMonth : key === current ? thisMonth : [];
    return { items, month: key, current_month: current, months: [current, previous] };
  }
  if (path.includes("/online")) return { members: online };
  if (path.includes("/summary")) {
    const month = new URL(path, "https://local.invalid").searchParams.get("month");
    const now = new Date();
    const current = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const prev = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const previous = `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`;
    const key = month && /^\d{4}-\d{2}$/.test(month) ? month : current;
    const past = key === previous;
    return {
      month_key: key,
      current_month: current,
      month_label: past ? "с 1 августа" : "с 1 сентября",
      day: [
        summaryMember(1, "Preview", 3, 70, 1),
        summaryMember(2, "Forrogmir", 2, 40),
        summaryMember(3, "HeCnu", 1, 20),
      ],
      month: past
        ? [
            summaryMember(1, "Preview", 8, 120, 1),
            summaryMember(2, "Forrogmir", 5, 90),
          ]
        : [
            summaryMember(1, "Preview", 21, 410, 4),
            summaryMember(2, "Forrogmir", 14, 260, 2),
            summaryMember(3, "HeCnu", 9, 150, 1),
          ],
      games: past ? games.slice(0, 2) : games,
    };
  }
  if (path.includes("/people")) return person;
  if (path === "/api/mini/admin") return adminHome;
  if (path === "/api/mini/admin/keys" || path.startsWith("/api/mini/admin/keys/")) return keys;
  if (path === "/api/mini/admin/limits") return { items: limits };
  if (path === "/api/mini/admin/defaults") return defaults;
  if (path === "/api/mini/admin/users") return { users: [adminUser] };
  if (path.startsWith("/api/mini/admin/users/")) return adminCard;
  if (path === "/api/mini/admin/chats") return { chats: [adminChat] };
  if (path.startsWith("/api/mini/admin/chats/") && method === "PATCH") return adminChat;
  if (path.includes("/actions")) return { ok: true, deleted: 0 };
  if (path.startsWith("/api/mini/hltb")) return path.includes("?") ? { results: [hltb] } : hltb;
  if (method === "PATCH" && path === "/api/mini/settings") {
    const raw = init?.body;
    const body = typeof raw === "string" ? (JSON.parse(raw) as Partial<MeResponse["settings"]>) : {};
    me.settings = { ...me.settings, ...body };
    return me;
  }
  if (method === "PATCH" && path.includes("/api/mini/club")) {
    const raw = init?.body;
    const body = typeof raw === "string" ? (JSON.parse(raw) as Record<string, unknown>) : {};
    const chat = me.chats[0];
    if (!chat) return { ok: true, chat: null };
    if (body.action === "subscribe") {
      chat.is_subscribed = true;
      chat.rarity_mode = chat.rarity_mode ?? "all";
      chat.digest_threshold = chat.digest_threshold ?? 3;
    } else if (body.action === "unsubscribe") {
      chat.is_subscribed = false;
      chat.rarity_mode = null;
      chat.digest_threshold = null;
    } else if (body.action === "set_rarity") {
      chat.rarity_mode = String(body.rarity_mode ?? "all");
    } else if (body.action === "set_digest") {
      chat.digest_threshold = Number(body.digest_threshold ?? 3);
    }
    return { ok: true, chat: { ...chat } };
  }
  if (method === "POST") return { ok: true, authorize_url: "https://example.com" };
  return { ok: true };
}
