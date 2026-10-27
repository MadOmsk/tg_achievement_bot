import { useEffect, useRef, useState } from "react";
import { useBackHandler } from "../core/back-stack";
import { VideoSlide, type Video } from "./VideoPlayer";

/** What the viewer shows: a picture's address, or a store's trailer. */
export type Media = string | Video;

type Shown = { list: Media[]; index: number };

let show: ((shown: Shown) => void) | null = null;

const keyOf = (m: Media) => (typeof m === "string" ? m : (m.hls ?? m.mp4 ?? m.poster ?? ""));

/** A picture or a trailer full screen, in the app — never sent to an outside
 * site. With a list (a game's gallery: its trailers and its pictures), a
 * finger slides to the next one. */
export function openImage(item: Media, list?: Media[]): void {
  const all = list && list.length ? list : [item];
  show?.({ list: all, index: Math.max(0, all.findIndex((m) => keyOf(m) === keyOf(item))) });
}

export function ImageViewer() {
  const [shown, setShown] = useState<Shown | null>(null);
  useEffect(() => {
    show = setShown;
    return () => {
      show = null;
    };
  }, []);
  if (!shown) return null;
  return <ViewerBody shown={shown} onClose={() => setShown(null)} />;
}

function ViewerBody({ shown, onClose }: { shown: Shown; onClose: () => void }) {
  useBackHandler(true, onClose, "viewer");
  const track = useRef<HTMLDivElement>(null);
  const [zoomed, setZoomed] = useState(false);
  const [at, setAt] = useState(shown.index);
  useEffect(() => {
    const node = track.current;
    if (node) node.scrollLeft = shown.index * node.clientWidth;
  }, [shown.index]);
  return (
    <div className="viewer" role="dialog" aria-modal="true">
      <div
        className={`viewer-track${zoomed ? " viewer-locked" : ""}`}
        ref={track}
        onScroll={(e) => setAt(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}
      >
        {shown.list.map((m, i) =>
          typeof m === "string" ? (
            <ZoomImage key={m} src={m} onClose={onClose} onZoom={setZoomed} />
          ) : (
            <VideoSlide key={keyOf(m)} video={m} active={i === at} onClose={onClose} />
          ),
        )}
      </div>
      {shown.list.length > 1 && (
        <div className="viewer-dots" aria-hidden="true">
          {shown.list.map((m, i) => (
            <span key={keyOf(m)} className={i === at ? "on" : ""} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Two fingers zoom and move the picture; a double tap zooms in or back; a
 * tap at its own size closes. */
function ZoomImage({ src, onClose, onZoom }: { src: string; onClose: () => void; onZoom: (on: boolean) => void }) {
  const [view, setView] = useState({ scale: 1, x: 0, y: 0 });
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ dist: number; scale: number; mid: { x: number; y: number }; x: number; y: number } | null>(null);
  const lastTap = useRef(0);
  const moved = useRef(false);

  const set = (next: { scale: number; x: number; y: number }) => {
    const scale = Math.min(5, Math.max(1, next.scale));
    const v = scale === 1 ? { scale: 1, x: 0, y: 0 } : { ...next, scale };
    setView(v);
    onZoom(v.scale > 1);
  };

  const points = () => [...pointers.current.values()];

  return (
    <div
      className="viewer-slide"
      onPointerDown={(e) => {
        pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
        moved.current = false;
        const p = points();
        if (p.length === 2) {
          gesture.current = {
            dist: Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y),
            scale: view.scale,
            mid: { x: (p[0].x + p[1].x) / 2, y: (p[0].y + p[1].y) / 2 },
            x: view.x,
            y: view.y,
          };
        } else if (p.length === 1 && view.scale > 1) {
          gesture.current = { dist: 0, scale: view.scale, mid: p[0], x: view.x, y: view.y };
        }
      }}
      onPointerMove={(e) => {
        if (!pointers.current.has(e.pointerId)) return;
        pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
        const g = gesture.current;
        if (!g) return;
        const p = points();
        moved.current = true;
        if (p.length === 2 && g.dist) {
          const dist = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
          const mid = { x: (p[0].x + p[1].x) / 2, y: (p[0].y + p[1].y) / 2 };
          set({ scale: (g.scale * dist) / g.dist, x: g.x + mid.x - g.mid.x, y: g.y + mid.y - g.mid.y });
        } else if (p.length === 1 && view.scale > 1) {
          set({ scale: view.scale, x: g.x + p[0].x - g.mid.x, y: g.y + p[0].y - g.mid.y });
        }
      }}
      onPointerUp={(e) => {
        pointers.current.delete(e.pointerId);
        if (pointers.current.size < 2) gesture.current = null;
        if (moved.current || pointers.current.size) return;
        const now = Date.now();
        if (now - lastTap.current < 280) {
          lastTap.current = 0;
          set(view.scale > 1 ? { scale: 1, x: 0, y: 0 } : { scale: 2.5, x: 0, y: 0 });
          return;
        }
        lastTap.current = now;
        window.setTimeout(() => {
          if (lastTap.current === now && view.scale === 1) onClose();
        }, 300);
      }}
      onPointerCancel={(e) => {
        pointers.current.delete(e.pointerId);
        gesture.current = null;
      }}
    >
      <img
        src={src}
        alt=""
        draggable={false}
        style={{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }}
      />
    </div>
  );
}
