import { useEffect, useState } from "react";
import { resolveHltb, searchHltb, type HltbHit } from "./api";
import { t, type Locale } from "./i18n";
import { GlassWait, Sheet } from "./ui";

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

export function GameHits({
  hits,
  busy,
  searched,
  locale,
  onOpen,
}: {
  hits: HltbHit[];
  busy: boolean;
  searched: boolean;
  locale: Locale;
  onOpen: (hit: HltbHit) => void;
}) {
  if (!busy && !searched) return null;
  return (
    <div className="game-hits">
      <p className="kicker">{t(locale, "games")}</p>
      {busy ? (
        <GlassWait />
      ) : hits.length === 0 ? (
        <p className="empty">{t(locale, "hltbEmpty")}</p>
      ) : (
        <div className="list">
          {hits.map((hit) => (
            <button
              key={hit.hltb_id}
              type="button"
              className="game-hit"
              onClick={() => onOpen(hit)}
            >
              {hit.image_url ? (
                <img src={hit.image_url} alt="" className="game-hit-art" />
              ) : (
                <span className="game-hit-art" />
              )}
              <span>
                <strong>{hit.name}</strong>
                <p className="muted tight">
                  {hit.release_year ?? "—"}
                  {hit.platforms[0] ? ` · ${hit.platforms[0]}` : ""}
                </p>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function GameSheet({
  preview,
  data,
  locale,
  onClose,
  onFlash,
}: {
  preview: HltbHit;
  data: string;
  locale: Locale;
  onClose: () => void;
  onFlash: (message: string) => void;
}) {
  const [game, setGame] = useState<HltbHit>(preview);
  const [descReady, setDescReady] = useState(Boolean(preview.description));

  useEffect(() => {
    let cancelled = false;
    setDescReady(Boolean(preview.description));
    void resolveHltb(data, preview.hltb_id)
      .then((full) => {
        if (cancelled) return;
        setGame(full);
        setDescReady(true);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setDescReady(true);
        onFlash(`${t(locale, "error")}: ${String(err)}`);
      });
    return () => {
      cancelled = true;
    };
  }, [data, preview.hltb_id, locale, onFlash, preview.description]);

  const cover = game.image_url || preview.image_url;
  const hours = (n: number | null) => (n == null ? "—" : `${n}`);
  const meta = [game.release_year, game.platforms[0], game.genre].filter(Boolean).join(" · ");
  const site = game.game_url || `https://howlongtobeat.com/game/${game.hltb_id}`;

  return (
    <Sheet mid onClose={onClose} closeLabel={t(locale, "close")} noClose>
      <div className="sheet-hltb">
        <div className="unlock-card hltb-sheet">
          <div className="unlock-card-art">
            <span className="profile-hero-layers">
              {cover ? (
                <img src={cover} alt="" draggable={false} className="profile-hero-art" />
              ) : (
                <span className="profile-hero-art home-banner-fallback" />
              )}
            </span>
            <span className="profile-hero-wash" />
            <div className="unlock-card-head">
              <span className="feed-post-lead">
                <button
                  type="button"
                  className="feed-post-who"
                  onClick={(e) => {
                    e.stopPropagation();
                    if (window.Telegram?.WebApp?.openLink) {
                      window.Telegram.WebApp.openLink(site);
                      return;
                    }
                    window.open(site, "_blank", "noopener");
                  }}
                >
                  <span className="hltb-ava" aria-hidden>
                    <svg viewBox="0 0 24 24" width="18" height="18">
                      <circle
                        cx="12"
                        cy="12"
                        r="8.2"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.75"
                      />
                      <path
                        d="M12 7.6v4.6l3.1 1.8"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.75"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                  <span>
                    <strong>HowLongToBeat</strong>
                  </span>
                </button>
              </span>
            </div>
            <div className="hltb-marks" aria-label={t(locale, "when")}>
              <span className="hltb-mark">
                <small>{t(locale, "hltbMain")}</small>
                <strong>
                  {hours(game.main_hours)}
                  {game.main_hours != null ? <em>{t(locale, "hours")}</em> : null}
                </strong>
              </span>
              <span className="hltb-mark">
                <small>{t(locale, "hltbExtra")}</small>
                <strong>
                  {hours(game.extra_hours)}
                  {game.extra_hours != null ? <em>{t(locale, "hours")}</em> : null}
                </strong>
              </span>
              <span className="hltb-mark">
                <small>{t(locale, "hltbComplete")}</small>
                <strong>
                  {hours(game.completionist_hours)}
                  {game.completionist_hours != null ? <em>{t(locale, "hours")}</em> : null}
                </strong>
              </span>
            </div>
          </div>
          <div className="unlock-card-copy">
            {cover ? (
              <img src={cover} alt="" className="unlock-card-copy-blur" draggable={false} />
            ) : (
              <span className="unlock-card-copy-blur home-banner-fallback" />
            )}
            <h2>
              <span>{game.name}</span>
            </h2>
            {meta ? <p className="hltb-copy-meta">{meta}</p> : null}
            {game.description ? (
              <p>{game.description}</p>
            ) : descReady ? null : (
              <GlassWait />
            )}
          </div>
        </div>
      </div>
    </Sheet>
  );
}
