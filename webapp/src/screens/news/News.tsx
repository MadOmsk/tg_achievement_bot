import type { NewsItem } from "../../api";
import { useApp } from "../../app/context";
import { tick } from "../../core/haptic";
import { whenLabel } from "../../i18n";
import { Cover } from "../../ui/Pic";
import { KindChip } from "../../parts/KindChip";
import "./News.css";

export function NewsCard({ item, compact = false }: { item: NewsItem; compact?: boolean }) {
  const { locale, open } = useApp();
  return (
    <button
      type="button"
      className={`news-card${compact ? " news-card-compact" : ""}`}
      onClick={() => {
        tick();
        open({ kind: "news", appid: item.appid, gid: item.gid, item, game: item.game });
      }}
    >
      {item.image && !compact && <Cover src={item.image} className="news-pic" />}
      <span className="news-body">
        <span className="news-meta">
          <KindChip kind={item.kind} />
          <span>
            {whenLabel(item.date, locale)}
          </span>
        </span>
        <span className="news-title clamp-3">{item.title}</span>
        {!compact && item.excerpt && <span className="news-excerpt clamp-3">{item.excerpt}</span>}
        {!compact && (
          <span className="news-game">
            <Cover src={item.game.icon_url} className="news-game-cover" />
            <span className="clamp-1">{item.game.name}</span>
          </span>
        )}
      </span>
    </button>
  );
}
