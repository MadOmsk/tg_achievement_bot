/** A store's name without its trademark signs: «Call of Duty®: Warzone™». */
export function cleanName(name: string): string {
  return name.replace(/[®™©]/g, "").replace(/\s{2,}/g, " ").trim();
}

const loose = (s: string) => cleanName(s).toLowerCase();

/** An add-on's own name: the game's name it opens with is taken off
 * («DEAD OR ALIVE 5 Last Round Ayane Maid Costume» → «Ayane Maid Costume»).
 * The longest of the game's names that opens it goes; nothing is left bare. */
export function addonName(name: string, gameNames: Array<string | null | undefined>): string {
  const clean = cleanName(name);
  const lower = clean.toLowerCase();
  const prefixes = gameNames
    .filter((n): n is string => Boolean(n))
    .map(loose)
    .sort((a, b) => b.length - a.length);
  for (const prefix of prefixes) {
    if (!lower.startsWith(prefix)) continue;
    const rest = clean.slice(prefix.length).replace(/^[\s:\-–—|,.]+/, "");
    if (rest.length >= 3) return rest;
  }
  return clean;
}

/** Trailers' names without what they all open with («Call of Duty: Modern
 * Warfare 4 - Campaign Trailer» → «Campaign Trailer»): the common start up to
 * its last « - », when every name has one after it. */
export function shortVideoNames<T extends { name?: string | null }>(videos: T[]): T[] {
  const names = videos.map((v) => (v.name ? cleanName(v.name) : null));
  const known = names.filter((n): n is string => Boolean(n));
  if (known.length < 2) return videos;
  let common = known[0];
  for (const n of known.slice(1)) {
    let i = 0;
    while (i < common.length && i < n.length && common[i] === n[i]) i += 1;
    common = common.slice(0, i);
  }
  const cut = common.lastIndexOf(" - ");
  if (cut < 0) return videos;
  const prefix = common.slice(0, cut + 3);
  if (known.some((n) => n.length - prefix.length < 3)) return videos;
  return videos.map((v, i) => (names[i] ? { ...v, name: names[i]!.slice(prefix.length) } : v));
}

/** A game's trailers as people read them: the game's name off the front
 * («Forever Ago - Launch Trailer» → «Launch Trailer»), a store's «Thumbnail»
 * tail off, and one trailer two stores both list shown once. */
export function tidyVideos<T extends { name?: string | null }>(videos: T[], gameNames: Array<string | null | undefined>): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const v of shortVideoNames(videos)) {
    const name = v.name ? addonName(v.name, gameNames).replace(/\s*thumbnail$/i, "").trim() : null;
    const key = (name ?? "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
    if (key && seen.has(key)) continue;
    if (key) seen.add(key);
    out.push({ ...v, name });
  }
  return out;
}
