import { gameArtOf, useArtTheme } from "../../app/artTheme";
import { useState } from "react";
import { useApp } from "../../app/context";
import { Section, Segmented } from "../../ui/Controls";
import { Page } from "../../ui/Page";
import type { Video } from "../../ui/VideoPlayer";
import { MediaTile } from "./MediaTile";
import { ListHead } from "./ListHead";
import "./Game.css";

type Show = "all" | "videos" | "shots";

/** A game's whole gallery on a page of its own: its trailers and its
 * pictures, one kind or both; a tap opens the viewer on what is shown. */
export function GalleryPage({
  game,
  cover,
  videos,
  screenshots,
  onClose,
  layer,
}: {
  game: string;
  cover: string | null;
  videos: Video[];
  screenshots: string[];
  onClose: () => void;
  layer: string;
}) {
  const { tr } = useApp();
  const both = videos.length > 0 && screenshots.length > 0;
  const [show, setShow] = useState<Show>("all");
  const list = show === "videos" ? videos : show === "shots" ? screenshots : [...videos, ...screenshots];
  const theme = useArtTheme(gameArtOf(game) ?? cover);
  return (
    <Page title={game} onBack={onClose} hero layer={layer} className="list-page" style={theme.style}>
      <ListHead game={game} cover={cover} label={`${tr("gpGallery")} · ${videos.length + screenshots.length}`} />
      {both && (
        <div className="list-filter">
          <Segmented
            options={[
              { value: "all", label: `${tr("gpAll")} ${videos.length + screenshots.length}` },
              { value: "videos", label: `${tr("gpVideos")} ${videos.length}` },
              { value: "shots", label: `${tr("gpShots")} ${screenshots.length}` },
            ]}
            value={show}
            onChange={setShow}
          />
        </div>
      )}
      {show !== "shots" && videos.length > 0 && (
        <Section title={tr("gpVideos")}>
          <div className={show === "videos" ? "gal-videos-col" : "rail gal-videos"}>
            {videos.map((v, i) => (
              <div key={v.hls ?? v.mp4 ?? i} className="gal-video">
                <MediaTile media={v} list={list} />
                {v.name && <span className="gal-video-name clamp-2">{v.name}</span>}
              </div>
            ))}
          </div>
        </Section>
      )}
      {show !== "videos" && screenshots.length > 0 && (
        <Section title={tr("gpShots")}>
          <div className="gp-gallery-grid">
            {screenshots.map((m) => (
              <MediaTile key={m} media={m} list={list} />
            ))}
          </div>
        </Section>
      )}
    </Page>
  );
}
