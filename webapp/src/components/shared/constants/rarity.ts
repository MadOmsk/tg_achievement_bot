// A person's publish filter for every chat (user_settings.rarity_mode on
// the bot side, #126) — the person only ever picks one of these three, never a percentage
// (see CLAUDE.md "Publication rules"). Centralized so the option values in
// the admin defaults screen and a person's own chat card can't drift apart.
export const RARITY_MODES = {
  ALL: "all",
  RARE: "rare",
  HIDDEN: "hidden",
} as const;

export type RarityMode = (typeof RARITY_MODES)[keyof typeof RARITY_MODES];
