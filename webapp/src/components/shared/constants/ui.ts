export const UI_CONFIG = {
  PULL_TO_REFRESH: {
    THRESHOLD: 68,
    MAX: 112,
  },
  AVATAR: {
    DEFAULT_SIZE: 44,
    ACCOUNT_BAR_SIZE: 48,
  },
  HOME: {
    MAX_CAROUSEL_SLIDES: 5,
  },
  STATS: {
    // Games listed on the stats screen before "see all".
    GAMES_PREVIEW: 6,
    // "Rare finds" counts an unlock only when fewer than this share of
    // players ever got it.
    RARE_FIND_PERCENT: 0.5,
    DAY_MS: 24 * 60 * 60 * 1000,
  },
} as const;
