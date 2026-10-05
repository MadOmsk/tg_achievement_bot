import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useBackHandler } from "../back-stack/backStack";
import "./ImageViewer.css";

const OPEN_EVENT = "image-viewer-open";
const MAX_SCALE = 5;
const DOUBLE_TAP_SCALE = 2.5;
const DOUBLE_TAP_MS = 280;

/** Show a picture full screen, in the app (owner, 2026-10-05): a picture in a
 * post, a guide or on a page opens here, not on Steam. */
export function openImage(src: string): void {
  window.dispatchEvent(new CustomEvent<string>(OPEN_EVENT, { detail: src }));
}

type Point = { x: number; y: number };

/** Mounted once, in the app shell: the full-screen picture `openImage` asks
 * for. Two fingers zoom and a finger moves it once zoomed; a double tap zooms
 * in or back; a tap at its own size or the phone's back closes it — nothing
 * drawn over the picture (owner, 2026-10-05). */
export function ImageViewerHost({ closeLabel }: { closeLabel: string }) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    const open = (event: Event) => setSrc((event as CustomEvent<string>).detail);
    window.addEventListener(OPEN_EVENT, open);
    return () => window.removeEventListener(OPEN_EVENT, open);
  }, []);

  if (!src) return null;
  return <Viewer key={src} src={src} closeLabel={closeLabel} onClose={() => setSrc(null)} />;
}

function Viewer({ src, closeLabel, onClose }: { src: string; closeLabel: string; onClose: () => void }) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState<Point>({ x: 0, y: 0 });
  const [moving, setMoving] = useState(false);
  const pointers = useRef(new Map<number, Point>());
  const pinch = useRef<{ distance: number; scale: number } | null>(null);
  const pan = useRef<{ start: Point; offset: Point } | null>(null);
  const lastTap = useRef(0);
  const tapTimer = useRef<number | null>(null);
  const moved = useRef(false);

  useBackHandler(true, onClose);

  useEffect(() => {
    document.documentElement.classList.add("is-sheet-open");
    return () => {
      document.documentElement.classList.remove("is-sheet-open");
      if (tapTimer.current) window.clearTimeout(tapTimer.current);
    };
  }, []);

  const reset = () => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
  };

  const distance = () => {
    const [a, b] = [...pointers.current.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };

  const onDown = (event: React.PointerEvent) => {
    (event.target as Element).setPointerCapture?.(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    moved.current = false;
    setMoving(true);
    if (pointers.current.size === 2) {
      pinch.current = { distance: distance(), scale };
      pan.current = null;
    } else if (pointers.current.size === 1) {
      pan.current = { start: { x: event.clientX, y: event.clientY }, offset };
    }
  };

  const onMove = (event: React.PointerEvent) => {
    if (!pointers.current.has(event.pointerId)) return;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pinch.current && pointers.current.size === 2) {
      moved.current = true;
      const next = (pinch.current.scale * distance()) / pinch.current.distance;
      setScale(Math.min(MAX_SCALE, Math.max(1, next)));
    } else if (pan.current && scale > 1) {
      const dx = event.clientX - pan.current.start.x;
      const dy = event.clientY - pan.current.start.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) moved.current = true;
      setOffset({ x: pan.current.offset.x + dx, y: pan.current.offset.y + dy });
    } else if (pan.current) {
      const dx = event.clientX - pan.current.start.x;
      const dy = event.clientY - pan.current.start.y;
      if (Math.abs(dx) + Math.abs(dy) > 8) moved.current = true;
    }
  };

  const onUp = (event: React.PointerEvent) => {
    pointers.current.delete(event.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
    if (pointers.current.size === 1) {
      const [rest] = [...pointers.current.values()];
      pan.current = { start: rest, offset };
      return;
    }
    pan.current = null;
    setMoving(false);
    if (scale <= 1.02) reset();
    if (moved.current) return;
    // A tap: a second one soon after zooms; one alone closes at its own size.
    const now = Date.now();
    if (now - lastTap.current < DOUBLE_TAP_MS) {
      lastTap.current = 0;
      if (tapTimer.current) window.clearTimeout(tapTimer.current);
      if (scale > 1) {
        reset();
      } else {
        const x = event.clientX - window.innerWidth / 2;
        const y = event.clientY - window.innerHeight / 2;
        setScale(DOUBLE_TAP_SCALE);
        setOffset({ x: -x * (DOUBLE_TAP_SCALE - 1), y: -y * (DOUBLE_TAP_SCALE - 1) });
      }
      return;
    }
    lastTap.current = now;
    if (scale <= 1.02) {
      tapTimer.current = window.setTimeout(onClose, DOUBLE_TAP_MS);
    }
  };

  return createPortal(
    <div
      className="image-viewer"
      role="dialog"
      aria-label={closeLabel}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      onPointerCancel={onUp}
      onClick={(event) => event.stopPropagation()}
    >
      <img
        src={src}
        alt=""
        draggable={false}
        className={moving ? "is-moving" : undefined}
        style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
      />
    </div>,
    document.body,
  );
}
