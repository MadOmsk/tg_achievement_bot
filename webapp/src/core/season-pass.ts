import { useEffect, useState } from "react";
import { passApi, type PassItemInput, type PassReward, type PassState, type PassTier, type Published } from "../api/season-pass/seasonPassApi";
import { look, setLook, type Palette } from "../app/env";
import type { TranslationKey } from "../i18n";

/** The season pass (owner, 2026-10-27): the month's points climb its levels,
 * each a theme of the app or a prize, claimed by a tap. The server keeps the
 * claims and judges them (`bot/services/season_pass.py`); the super-admin
 * edits the levels as a draft and publishes it. Violet is everybody's. */
export type Tier = PassTier & { palette: Palette };

export const DEFAULT_PALETTE: Palette = "violet";

// One answer for every screen that shows the pass, so a claim on one is seen
// on the others at once.
let cached: PassState | null = null;
const listeners = new Set<(state: PassState) => void>();
// While a screen shows the pass it is asked again now and then and on coming
// back to the app, so a reward the super-admin adds shows with no reload.
const REFRESH_MS = 60_000;
let refresher: number | null = null;
let refreshData = "";
// The month the super-admin's editor shows; null: this one.
let editMonth: string | null = null;

function publish(state: PassState): void {
  cached = state;
  // A theme on the device that the server does not give is taken off.
  const palette = look().palette;
  if (palette !== DEFAULT_PALETTE && !state.tiers.some((t) => t.palette === palette && t.claimed)) {
    setLook({ palette: DEFAULT_PALETTE });
  }
  for (const fn of listeners) fn(state);
}

function refresh(): void {
  passApi.fetchPass(refreshData, { edit: editMonth }).then(publish, () => undefined);
}

function onShown(): void {
  if (document.visibilityState === "visible") refresh();
}

export function usePass(initData: string): PassState | null {
  const [state, setState] = useState(cached);
  useEffect(() => {
    listeners.add(setState);
    refreshData = initData;
    refresh();
    if (refresher == null) {
      refresher = window.setInterval(() => {
        if (document.visibilityState === "visible") refresh();
      }, REFRESH_MS);
      document.addEventListener("visibilitychange", onShown);
    }
    return () => {
      listeners.delete(setState);
      if (!listeners.size && refresher != null) {
        window.clearInterval(refresher);
        refresher = null;
        document.removeEventListener("visibilitychange", onShown);
      }
    };
  }, [initData]);
  return state;
}

/** The editor on another month's pass: this one or the next. */
export async function setEditMonth(initData: string, month: string | null): Promise<void> {
  editMonth = month;
  publish(await passApi.fetchPass(initData, { edit: month }));
}

/** The edited month's pass's name, waiting for its publish; empty clears it. */
export async function setSeasonTitle(initData: string, title: string): Promise<void> {
  publish(await passApi.seasonTitle(initData, editMonth, title));
}

/** The edited month's cover, waiting for its publish; null takes it off. */
export async function setSeasonImage(initData: string, image: Blob | null): Promise<void> {
  publish(await passApi.seasonImage(initData, editMonth, image));
}

export async function claimReward(initData: string, id: number): Promise<void> {
  publish(await passApi.claimReward(initData, id));
}

// The super-admin's editor: every call answers with the whole pass again.
export async function saveItem(initData: string, id: number | null, item: PassItemInput, image?: Blob | null): Promise<void> {
  const state = id == null ? await passApi.addItem(initData, editMonth, item) : await passApi.editItem(initData, editMonth, id, item);
  publish(state);
  const target = id ?? (state as PassState & { added?: number }).added;
  if (image && target != null) publish(await passApi.putItemImage(initData, editMonth, target, image));
}

export async function removeItem(initData: string, id: number): Promise<void> {
  publish(await passApi.removeItem(initData, editMonth, id));
}

export async function revertItem(initData: string, id: number): Promise<void> {
  publish(await passApi.revertItem(initData, editMonth, id));
}

export async function publishPass(initData: string, notify: boolean): Promise<Published> {
  const state = await passApi.publish(initData, editMonth, notify);
  publish(state);
  return state.published;
}

export async function discardPass(initData: string): Promise<void> {
  publish(await passApi.discard(initData, editMonth));
}

/** A reward the viewer could take now: points enough, codes left, none yet. */
export function rewardOpen(r: PassReward, points: number): boolean {
  return !r.code && !r.removed && r.left > 0 && points >= r.points;
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
  const rewards = state?.rewards ?? [];
  // What the door's badge counts: the themes and the rewards to take now.
  const due = waiting.length + rewards.filter((r) => rewardOpen(r, points)).length;
  return { tiers, points, level, next, from, toNext: next ? next.points - points : 0, waiting, rewards, due };
}

export const PALETTE_NAMES = {
  violet: "paletteViolet",
  mint: "paletteMint",
  ember: "paletteEmber",
  ocean: "paletteOcean",
  rose: "paletteRose",
  graphite: "paletteGraphite",
  halloween: "paletteHalloween",
} as const satisfies Record<Palette, TranslationKey>;
