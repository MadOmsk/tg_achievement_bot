import { useCallback, useEffect, useRef, useState } from "react";

export type Loaded<T> = {
  data: T | undefined;
  error: unknown;
  loading: boolean;
  reload: () => void;
  set: (data: T) => void;
};

/** Ask the server whenever `key` changes; the last answer stays on screen
 * while the next one comes (no flash of emptiness), and a late answer to an
 * older key is dropped. `initial` draws at once (a cache). */
export function useLoad<T>(key: string | null, fetcher: () => Promise<T>, initial?: T): Loaded<T> {
  const [data, setData] = useState<T | undefined>(initial);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(key !== null);
  const [round, setRound] = useState(0);
  const latest = useRef(fetcher);
  latest.current = fetcher;
  useEffect(() => {
    if (key === null) return;
    let live = true;
    setLoading(true);
    setError(null);
    latest
      .current()
      .then((value) => {
        if (!live) return;
        setData(value);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (!live) return;
        setError(err);
        setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [key, round]);
  const reload = useCallback(() => setRound((n) => n + 1), []);
  return { data, error, loading, reload, set: setData };
}
