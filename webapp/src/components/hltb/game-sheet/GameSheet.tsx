import { useEffect, useState } from "react";
import { resolveHltb, type HltbHit } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { CoverImg, FitImg, GlassWait, Sheet } from "../../shared/lib";

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
  const meta = [game.release_year, game.platforms[0], game.genre]
    .filter(Boolean)
    .join(" · ");
  const site =
    game.game_url || `https://howlongtobeat.com/game/${game.hltb_id}`;

  return (
    <Sheet mid onClose={onClose} closeLabel={t(locale, "close")} noClose>
      <div className="sheet-hltb">
        <div className="unlock-card hltb-sheet has-fit">
          <div className="unlock-card-art">
            <span className="profile-hero-layers">
              <CoverImg src={cover} kind="game" className="profile-hero-art" />
            </span>
            <span className="profile-hero-wash" />
          </div>
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
          <div className="unlock-card-fit hltb-fit">
            <FitImg src={cover} mode="width" kind="game" />
            <div className="hltb-marks" aria-label={t(locale, "when")}>
              <span className="hltb-mark">
                <small>{t(locale, "hltbMain")}</small>
                <strong>
                  {hours(game.main_hours)}
                  {(game.main_hours != null) && <em>{t(locale, "hours")}</em>}
                </strong>
              </span>
              <span className="hltb-mark">
                <small>{t(locale, "hltbExtra")}</small>
                <strong>
                  {hours(game.extra_hours)}
                  {(game.extra_hours != null) && <em>{t(locale, "hours")}</em>}
                </strong>
              </span>
              <span className="hltb-mark">
                <small>{t(locale, "hltbComplete")}</small>
                <strong>
                  {hours(game.completionist_hours)}
                  {(game.completionist_hours != null) && (
                    <em>{t(locale, "hours")}</em>
                  )}
                </strong>
              </span>
            </div>
          </div>
          <div className="unlock-card-copy">
            <h2>
              <span>{game.name}</span>
            </h2>
            {meta && <p className="hltb-copy-meta">{meta}</p>}
            {game.description ? (
              <p>{game.description}</p>
            ) : !descReady && (
              <GlassWait />
            )}
          </div>
        </div>
      </div>
    </Sheet>
  );
}
