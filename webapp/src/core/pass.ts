import { useEffect, useState } from "react";
import { passApi, type PassState, type PassTier } from "../api/pass/passApi";
import { look, setLook, type Palette } from "../app/env";
import type { TranslationKey } from "../i18n";

/** The season pass (owner, 2026-10-27): the month's points climb its levels,
 * and each level reached gives one of the app's themes to claim. The server
 * keeps the claims and judges them (`bot/services/season_pass.py`); Violet is
 * everybody's. Every month runs the same levels again. */
export type Tier = PassTier & { palette: Palette };

export const DEFAULT_PALETTE: Palette = "violet";

// One answer for every screen that shows the pass, so a claim on one is seen
// on the others at once.
let cached: PassState | null = null;
const listeners = new Set<(state: PassState) => void>();

function publish(state: PassState): void {
  cached = state;
  // A theme on the device that the server does not give is taken off.
  const palette = look().palette;
  if (palette !== DEFAULT_PALETTE && !state.tiers.some((t) => t.palette === palette && t.claimed)) {
    setLook({ palette: DEFAULT_PALETTE });
  }
  for (const fn of listeners) fn(state);
}

export function usePass(initData: string): PassState | null {
  const [state, setState] = useState(cached);
  useEffect(() => {
    listeners.add(setState);
    passApi.fetchPass(initData).then(publish, () => undefined);
    return () => {
      listeners.delete(setState);
    };
  }, [initData]);
  return state;
}

export async function claimTheme(initData: string, palette: Palette): Promise<void> {
  publish(await passApi.claim(initData, palette));
}

export function tiersOf(state: PassState | null): Tier[] {
  return (state?.tiers ?? []) as Tier[];
}

export function paletteOpen(palette: Palette, state: PassState | null): boolean {
  if (palette === DEFAULT_PALETTE) return true;
  return Boolean(state?.tiers.some((t) => t.palette === palette && t.claimed));
}

export function paletteLevel(palette: Palette, state: PassState | null): number | null {
  return state?.tiers.find((t) => t.palette === palette)?.level ?? null;
}

/** Where the month's points stand: the level, and how far to the next. */
export function passProgress(state: PassState | null) {
  const tiers = tiersOf(state);
  const points = state?.points ?? 0;
  const level = tiers.filter((t) => points >= t.points).length;
  const next = tiers[level] ?? null;
  const from = level > 0 ? tiers[level - 1].points : 0;
  const waiting = tiers.filter((t) => points >= t.points && !t.claimed);
  return { tiers, points, level, next, from, toNext: next ? next.points - points : 0, waiting };
}

export const PALETTE_NAMES = {
  violet: "paletteViolet",
  mint: "paletteMint",
  ember: "paletteEmber",
  ocean: "paletteOcean",
  rose: "paletteRose",
  graphite: "paletteGraphite",
} as const satisfies Record<Palette, TranslationKey>;
