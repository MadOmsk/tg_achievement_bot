import { useApp } from "../../app/context";
import { Icon } from "../../ui/Icon";
import { openImage, type Media } from "../../ui/Viewer";

/** One picture or trailer of a game's gallery; a tap opens the whole gallery
 * at it. */
export function MediaTile({ media, list, className = "" }: { media: Media; list: Media[]; className?: string }) {
  const { tr } = useApp();
  if (typeof media === "string") {
    return (
      <button type="button" className={`gp-shot ${className}`} onClick={() => openImage(media, list)}>
        <img src={media} alt="" loading="lazy" />
      </button>
    );
  }
  return (
    <button type="button" className={`gp-shot gp-video ${className}`} aria-label={media.name ?? tr("video")} onClick={() => openImage(media, list)}>
      {media.poster ? <img src={media.poster} alt="" loading="lazy" /> : <span className="gp-video-blank" />}
      <span className="gp-video-play shape-cookie9">
        <Icon name="play" size={24} />
      </span>
      {media.name && <span className="gp-video-name clamp-1">{media.name}</span>}
    </button>
  );
}
