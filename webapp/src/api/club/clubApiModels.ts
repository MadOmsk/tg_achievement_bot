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
  month: { count: number; score: number; xbox: number; steam: number; psn: number };
  month_key?: string;
  current_month?: string;
  months?: string[];
  games: Array<{
    title_id?: string | null;
    name: string | null;
    unlocked: number | null;
    gamerscore: number | null;
    platform: string | null;
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
  games: SummaryGame[];
};
