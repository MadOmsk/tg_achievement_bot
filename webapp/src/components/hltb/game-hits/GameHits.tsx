import type { HltbHit } from "../../../api";
import { t, type Locale } from "../../../i18n";
import { CoverImg, GlassWait, Row, RowsSection } from "../../shared/lib";

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
      <RowsSection title={t(locale, "games")}>
        {busy ? (
          <GlassWait />
        ) : hits.length === 0 ? (
          <p className="empty">{t(locale, "hltbEmpty")}</p>
        ) : (
          hits.map((hit) => (
            <Row
              key={hit.hltb_id}
              lead={
                <CoverImg
                  src={hit.image_url}
                  kind="game"
                  className="rows-art is-cover"
                />
              }
              title={hit.name}
              subtitle={[hit.release_year ?? "—", hit.platforms[0]]
                .filter(Boolean)
                .join(" · ")}
              onClick={() => onOpen(hit)}
            />
          ))
        )}
      </RowsSection>
    </div>
  );
}
