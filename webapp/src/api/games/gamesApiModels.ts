export type GameRef = {
  platform: string;
  title_id: string;
  name?: string | null;
  icon_url?: string | null;
  cover?: string | null;
  /** Whose card it was opened from: their progress is shown first. */
  person?: { tg_id: number; name: string } | null;
};

export type GameAchievement = {
  achievement_id: string;
  name_ru: string | null;
  name_en: string | null;
  description_ru: string | null;
  description_en: string | null;
  icon_url: string | null;
  is_secret: boolean;
  score?: number | null;
  gamerscore?: number | null;
  trophy_type: string | null;
  trophy_group_id?: string | null;
  rarity_mode?: string | null;
  rarity_percent: number | null;
  is_unlocked: boolean;
  unlocked_at: string | null;
};

export type GameGroup = {
  group_id: string;
  name: string | null;
  total: number | null;
  name_ru: string | null;
  name_en: string | null;
};

export type GameHltb = {
  hltb_id: number;
  name: string;
  release_year: number | null;
  main_hours: number | null;
  extra_hours: number | null;
  completionist_hours: number | null;
  genre: string | null;
  description: string | null;
  game_url: string | null;
  details?: GameHltbDetails | null;
};

export type HltbTimeBucket = {
  average?: number;
  median?: number;
  fastest?: number;
  slowest?: number;
};

export type HltbTimeName = "main" | "extra" | "completionist" | "all" | "coop" | "multi";

/** The rest of the game's HLTB page; every field is left out when HLTB has nothing for it. */
export type GameHltbDetails = {
  review_score?: number;
  developer?: string;
  publisher?: string;
  alias?: string;
  releases?: Partial<Record<"world" | "na" | "eu" | "jp", string>>;
  modes?: Array<"single" | "coop" | "multi">;
  times?: Partial<Record<HltbTimeName, HltbTimeBucket>>;
  speedrun?: Partial<Record<"any" | "full", { best?: number; median?: number }>>;
};

export type GameDetails = {
  ok: boolean;
  platform: string;
  title_id: string;
  name: string | null;
  name_ru: string | null;
  name_en: string | null;
  icon_url: string | null;
  cover_path: string | null;
  achievements_total: number;
  achievements_unlocked: number;
  completion_percent: number;
  /** The catalog holds fewer achievements than the game has (not fully loaded yet). */
  catalog_partial?: boolean;
  achievements_checked_at: string | null;
  groups: GameGroup[];
  achievements: GameAchievement[];
};

export type GameHltbResponse = {
  ok: boolean;
  hltb: GameHltb | null;
};
