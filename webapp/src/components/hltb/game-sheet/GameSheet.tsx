import { useEffect, useState } from "react";
import { resolveHltb, type HltbHit } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { createPortal } from "react-dom";
import { BackHead, CoverImg, FitImg, GlassWait, Icon, openImage, useImageRatio } from "../../shared/lib";
import { openUrl } from "../../game/rich-text/RichText";
import "../../game/post-page/PostPage.css";

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
  const ratio = useImageRatio(cover, { fallback: 16 / 9 });
  const hours = (n: number | null) => (n == null ? "—" : `${n}`);
  const meta = [game.release_year, game.platforms[0]]
    .filter(Boolean)
    .join(" · ");
  const site =
    game.game_url || `https://howlongtobeat.com/game/${game.hltb_id}`;

  const time = (key: "hltbMain" | "hltbExtra" | "hltbComplete", n: number | null) => (
    <div className="hltb-time">
      <p>{t(locale, key)}</p>
      <strong>
        {hours(n)}
        {n != null && <em>{t(locale, "hours")}</em>}
      </strong>
    </div>
  );

  // A page as a post's is (owner, 2026-10-07): the picture whole, edge to
  // edge, then what the game is, its hours, its story and the way to HLTB.
  return createPortal(
    <div className="post-page" data-no-pull>
      <BackHead title={game.name} backLabel={t(locale, "back")} onBack={onClose} />
      {cover && (
        <div className="post-page-pic" style={{ aspectRatio: ratio }} onClick={() => openImage(cover)}>
          <CoverImg src={cover} kind="game" className="post-page-back" />
          <FitImg src={cover} kind="game" mode="contain" />
        </div>
      )}
      <article className="post-page-body">
        {meta && <div className="post-page-meta">{meta}</div>}
        <h2 className="post-page-title">{game.name}</h2>
        <div className="hltb-times" aria-label={t(locale, "when")}>
          {time("hltbMain", game.main_hours)}
          {time("hltbExtra", game.extra_hours)}
          {time("hltbComplete", game.completionist_hours)}
        </div>
        {game.description ? (
          <p className="post-page-lead">{game.description}</p>
        ) : (
          !descReady && <GlassWait />
        )}
        <button type="button" className="see-all post-page-steam" onClick={() => openUrl(site)}>
          <span>{t(locale, "hltbOnSite")}</span>
          <Icon name="forward" size={16} />
        </button>
      </article>
    </div>,
    document.body,
  );
}
