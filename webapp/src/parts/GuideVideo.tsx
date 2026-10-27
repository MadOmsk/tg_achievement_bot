import type { GameGuide } from "../api/games/gamesApiModels";
import { useApp } from "../app/context";
import { openExternal } from "../app/env";
import { Icon } from "../ui/Icon";
import { LinkCard } from "../ui/LinkCard";

/** A game's own guide video, as every link is drawn: its picture (or the
 * channel's mark when no one video covers the game), "Video guide" and the
 * channel, a play mark; it opens on YouTube. */
export function GuideVideo({ guide }: { guide: GameGuide }) {
  const { tr } = useApp();
  return (
    <LinkCard
      wide={Boolean(guide.video_id)}
      media={
        guide.video_id ? (
          <img src={`https://i.ytimg.com/vi/${guide.video_id}/mqdefault.jpg`} alt="" loading="lazy" className="link-card-thumb" />
        ) : (
          <span className="link-card-icon">
            <Icon name="play" size={22} />
          </span>
        )
      }
      title={tr("gameGuideVideo")}
      sub={guide.title ? `${guide.channel} · ${guide.title}` : guide.channel}
      go="play"
      onOpen={() => openExternal(guide.url)}
    />
  );
}
