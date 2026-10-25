import { useEffect, useState } from "react";
import { gameApi, type GameCard } from "../../../api";
import { t, type Locale } from "../../../i18n";

/** Games of our own catalog by name (owner, 2026-10-25: never a search on the
 * internet), from two letters, a moment after the last keystroke. */
export function useGameSearch(
  data: string,
  query: string,
  locale: Locale,
  onFlash: (message: string) => void,
) {
  const [hits, setHits] = useState<GameCard[]>([]);
  const [busy, setBusy] = useState(false);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setHits([]);
      setSearched(false);
      setBusy(false);
      return;
    }
    setBusy(true);
    setSearched(false);
    let cancelled = false;
    const id = window.setTimeout(() => {
      void gameApi
        .searchGames(data, q)
        .then((payload) => {
          if (cancelled) return;
          setHits(payload.games);
          setSearched(true);
          setBusy(false);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setBusy(false);
          onFlash(`${t(locale, "error")}: ${String(err)}`);
        });
    }, 220);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [query, data, locale, onFlash]);

  return { hits, busy, searched };
}
