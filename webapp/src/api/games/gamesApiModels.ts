export type GameRef = {
  /** The game itself (a search hit, a series): a ref with only this opens it. */
  game_id?: number;
  platform: string;
  title_id: string;
  name?: string | null;
  icon_url?: string | null;
  cover?: string | null;
  /** Whose card it was opened from: their progress is shown first. A post's
   * button from before person ids (#156) knows only their Telegram id. */
  person?: { person_id?: number; tg_id?: number; name: string } | null;
};

export type GameAchievement = {
  achievement_id: string;
  name_ru: string | null;
  name_en: string | null;
  description_ru: string | null;
  description_en: string | null;
  /** Its Russian is on its way: it shows blurred. */
  translating?: boolean;
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

export type GameDetails = {
  ok: boolean;
  /** The list's descriptions are on their way: what has no Russian shows blurred. */
  translating?: boolean;
  /** Whose progress this is, when not the viewer's own. */
  viewed?: { person_id: number; name: string } | null;
  platform: string;
  title_id: string;
  name: string | null;
  name_ru: string | null;
  name_en: string | null;
  icon_url: string | null;
  cover_path: string | null;
  /** The catalog's game the list is of (none while it is in no game). */
  game?: { game_id: number; name: string | null; poster: string | null; hero: string | null } | null;
  achievements_total: number;
  achievements_unlocked: number;
  completion_percent: number;
  /** The catalog holds fewer achievements than the game has (not fully loaded yet). */
  catalog_partial?: boolean;
  achievements_checked_at: string | null;
  groups: GameGroup[];
  achievements: GameAchievement[];
};

/** What the Steam community's guides say about one achievement. */
export type AchievementTip = {
  text: string;
};

export type GameGuide = {
  url: string;
  channel: string;
  /** How many of the channel's videos are about the game. */
  count: number;
  video_id: string | null;
  title: string | null;
};

/** A guide video that names one achievement: where in it to start. */
export type AchievementVideo = {
  id: string;
  title: string;
  channel: string;
  /** Seconds into the video. */
  start: number;
  /** "PART 2" of a guide in several; 0 when it is one. */
  part: number;
  url: string;
};

/** The tip for every achievement of the game that has one, by achievement id. */
export type GameGuidesResponse = {
  ok: boolean;
  tips: Record<string, AchievementTip>;
  /** Guide videos by achievement id. */
  videos?: Record<string, AchievementVideo[]>;
  /** The game's guide on a guide channel: a whole-game video, or the
   * channel's search for the game. */
  guide?: GameGuide | null;
  /** False while Steam still holds some guides back; asking again later finds more. */
  complete: boolean;
};
