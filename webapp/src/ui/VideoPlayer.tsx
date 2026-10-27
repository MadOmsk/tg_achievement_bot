import { useEffect, useRef, useState } from "react";
import { useApp } from "../app/context";
import { Icon } from "./Icon";

export type Video = { name: string | null; mp4: string | null; hls: string | null; poster: string | null };

/** One trailer as a slide of the viewer: it plays while it is the slide
 * shown, and stops when a finger slides on. */
export function VideoSlide({ video, active, onClose }: { video: Video; active: boolean; onClose: () => void }) {
  const { tr } = useApp();
  const node = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = node.current;
    if (!el) return;
    if (video.mp4) {
      el.src = video.mp4;
      return;
    }
    if (!video.hls) return;
    // hls.js wherever the browser has Media Source (Android's WebView says it
    // plays HLS and then fails on the stores' fMP4 streams); the browser's own
    // player only where there is none — an iPhone, which plays them itself.
    let player: { destroy: () => void } | null = null;
    let live = true;
    void import("hls.js").then(({ default: Hls }) => {
      if (!live) return;
      if (!Hls.isSupported()) {
        if (el.canPlayType("application/vnd.apple.mpegurl")) el.src = video.hls!;
        else setFailed(true);
        return;
      }
      const hls = new Hls();
      hls.on(Hls.Events.ERROR, (_e, data) => data.fatal && setFailed(true));
      hls.loadSource(video.hls!);
      hls.attachMedia(el);
      player = hls;
    });
    return () => {
      live = false;
      player?.destroy();
    };
  }, [video]);

  useEffect(() => {
    const el = node.current;
    if (!el) return;
    if (active) void el.play().catch(() => undefined);
    else el.pause();
  }, [active]);

  return (
    <div className="viewer-slide viewer-video">
      <video
        ref={node}
        className="video-el"
        poster={video.poster ?? undefined}
        controls
        playsInline
        preload="metadata"
        onError={() => setFailed(true)}
      />
      {failed && <p className="video-failed">{tr("videoFailed")}</p>}
      <button type="button" className="viewer-close" aria-label={tr("close")} onClick={onClose}>
        <Icon name="close" size={22} />
      </button>
    </div>
  );
}
