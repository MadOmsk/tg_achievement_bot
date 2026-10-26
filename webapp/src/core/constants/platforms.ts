export const PLATFORMS = {
  XBOX: "xbox",
  XBOX_MODERN: "xbox_modern",
  XBOX_360: "xbox_360",
  STEAM: "steam",
  PSN: "psn",
} as const;

export type PlatformId = (typeof PLATFORMS)[keyof typeof PLATFORMS];

export const COMPLETION_BADGES = {
  XBOX: "🌀",
  STEAM: "👾",
  PSN: "💠",
} as const;

export const TROPHY_BADGES = {
  BRONZE: "🥉",
  SILVER: "🥈",
  GOLD: "🥇",
  PLATINUM: "💠",
} as const;
