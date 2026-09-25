import { useEffect, useState } from "react";
import { searchHltb, type HltbHit } from "../../api";
import { t, type Locale } from "../../i18n";

export function useHltbSearch(
  data: string,
  query: string,
  locale: Locale,
  onFlash: (message: string) => void,
) {
  const [hits, setHits] = useState<HltbHit[]>([]);
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
    setHits([]);
    let cancelled = false;
    const id = window.setTimeout(() => {
      void searchHltb(data, q)
        .then((payload) => {
          if (cancelled) return;
          setHits(payload.results);
          setSearched(true);
          setBusy(false);
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          setBusy(false);
          onFlash(`${t(locale, "error")}: ${String(err)}`);
        });
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(id);
    };
  }, [query, data, locale, onFlash]);

  return { hits, busy, searched };
}
