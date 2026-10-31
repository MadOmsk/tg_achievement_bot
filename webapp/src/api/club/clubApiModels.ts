export type FeedProgress = {
  unlocked: number;
  total: number;
  /** PSN title split into base + DLC/mode — overall count includes them. */
  has_dlc?: boolean;
  group?: {
    name: string;
    unlocked: number;
    total: number;
    is_default?: boolean;
  } | null;
};

export type FeedItem = {
  person_id: number;
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
  /** The catalog's game: what opens, and its pictures (none for a list in no game yet). */
  game_id?: number | null;
  game_poster?: string | null;
  game_hero?: string | null;
  description: string | null;
  trophy_type: string | null;
  tier_badge: string | null;
  mythic?: boolean;
  progress?: FeedProgress | null;
};

export type OnlineMember = {
  person_id: number;
  name: string;
  state: string | null;
  platform: string;
  title_name: string | null;
  playing: boolean;
  status: string;
  icon: string;
};

export type SummaryMember = {
  person_id: number;
  name: string;
  count: number;
  score: number;
  points?: number;
  rare: number;
  xbox: number;
  steam: number;
  psn: number;
};

export type SummaryGame = {
  /** The catalog's game; none for a list in no game yet. */
  game_id?: number | null;
  title_id: string;
  platform: string;
  name: string | null;
  count: number;
  score: number;
  icon_url?: string | null;
};

/** One platform's achievement list of a month's game: its own count. */
export type MonthGameList = { platform: string; title_id: string; unlocked: number };

export type PersonPayload = {
  person_id: number;
  name: string;
  /** The owner keeps their activity private: only the name is real (#157). */
  hidden?: boolean;
  presence?: {
    state: string | null;
    playing: boolean;
    platform: string | null;
    title_name?: string | null;
  } | null;
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
  month: { count: number; score: number; points?: number; xbox: number; steam: number; psn: number };
  month_key?: string;
  current_month?: string;
  months?: string[];
  games: Array<{
    title_id?: string | null;
    name: string | null;
    unlocked: number | null;
    gamerscore: number | null;
    platform: string | null;
    poster?: string | null;
    game_id?: number | null;
    lists?: MonthGameList[];
  }>;
  feed: FeedItem[];
};

export type FeedResponse = {
  items: FeedItem[];
  month: string;
  current_month: string;
  months: string[];
};

export type SummaryResponse = {
  month_key: string;
  current_month: string;
  month_label: string;
  day: SummaryMember[];
  month: SummaryMember[];
  /** The year of the month shown, up to that month's end. */
  year?: SummaryMember[];
  year_key?: number;
  games: SummaryGame[];
  /** The month's unlocks of everybody, newest first ("hunting together" is
   * read from them). */
  recent?: FeedItem[];
  /** The month's rarest finds. */
  rares?: FeedItem[];
};

/** A post of a game's developer on Steam (owner, 2026-10-05), untranslated. */
export type NewsItem = {
  gid: string;
  appid: number;
  kind: "patch" | "news";
  title: string;
  /** ISO date. */
  date: string;
  excerpt: string;
  /** The whole post: pictures and videos on lines of their own. */
  text: string;
  image: string | null;
  /** The post on Steam. */
  url: string;
  /** `hero`: the game's wide art, for a post with no picture of its own. */
  game: { game_id?: number | null; platform: string; title_id: string; name: string; icon_url: string | null; hero?: string | null };
};

export type NewsResponse = {
  items: NewsItem[];
  month: string;
  current_month: string;
  months: string[];
};

/** A game's developer post, opened whole. */
export type NewsPost = {
  title: string;
  /** ISO date. */
  date: string;
  /** The whole post: pictures and videos on lines of their own. */
  text: string;
  image: string | null;
  /** The post on Steam. */
  url: string;
  kind?: "patch" | "news";
};
