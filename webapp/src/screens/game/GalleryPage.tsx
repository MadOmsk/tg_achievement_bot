import { gameArtOf, useArtTheme } from "../../app/artTheme";
import { useState } from "react";
import { useApp } from "../../app/context";
import { Segmented } from "../../ui/Controls";
import { Hero } from "../../ui/Hero";
import { Page } from "../../ui/Page";
import { Cover } from "../../ui/Pic";
import type { Video } from "../../ui/VideoPlayer";
import { MediaTile } from "./MediaTile";
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
      <Hero ground={cover}>
        <Cover src={cover} className="gallery-cover" />
        <p className="list-name t-title clamp-2">{game}</p>
        <p className="gallery-sub">
          {tr("gpGallery")} · {videos.length + screenshots.length}
        </p>
      </Hero>
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
      <div className="gp-gallery-grid">
        {list.map((m, i) => (
          <MediaTile key={typeof m === "string" ? m : (m.hls ?? m.mp4 ?? i)} media={m} list={list} />
        ))}
      </div>
    </Page>
  );
}
