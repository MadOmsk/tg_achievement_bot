/** What a game's page last showed, kept for the session so opening a game
 * again draws at once from it while the fresh answers come in behind — the
 * page used to wait for four requests every time, whatever it had shown a
 * minute before. Small: the last few games only. */
const KEPT = 30;

const shelves = new Map<string, Map<string, unknown>>();

function shelf(name: string): Map<string, unknown> {
  let map = shelves.get(name);
  if (!map) {
    map = new Map();
    shelves.set(name, map);
  }
  return map;
}

export function recall<T>(name: string, key: string): T | undefined {
  return shelf(name).get(key) as T | undefined;
}

export function remember<T>(name: string, key: string, value: T): void {
  const map = shelf(name);
  map.delete(key);
  map.set(key, value);
  // Oldest out first: a Map keeps insertion order.
  while (map.size > KEPT) {
    const oldest = map.keys().next().value;
    if (oldest === undefined) break;
    map.delete(oldest);
  }
}
