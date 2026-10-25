import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useBackHandler } from "../back-stack/backStack";
import "./ImageViewer.css";

const OPEN_EVENT = "image-viewer-open";
const MAX_SCALE = 5;
const DOUBLE_TAP_SCALE = 2.5;
const DOUBLE_TAP_MS = 280;
// How far a finger slides a picture at its own size to step to the next one.
const SWIPE_PX = 64;

type Opened = { src: string; list: string[] };

/** Show a picture full screen, in the app (owner, 2026-10-05): a picture in a
 * post, a guide or on a page opens here, not on Steam. */
export function openImage(src: string, list?: string[]): void {
  const detail: Opened = { src, list: list && list.includes(src) ? list : [src] };
  window.dispatchEvent(new CustomEvent<Opened>(OPEN_EVENT, { detail }));
}

type Point = { x: number; y: number };

/** Mounted once, in the app shell: the full-screen picture `openImage` asks
 * for. Two fingers zoom and a finger moves it once zoomed; a double tap zooms
 * in or back; a tap at its own size or the phone's back closes it — nothing
 * drawn over the picture (owner, 2026-10-05). Opened with a list (a game's
 * screenshots), a finger slides from one to the next (owner, 2026-10-26). */
export function ImageViewerHost({ closeLabel }: { closeLabel: string }) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const open = (event: Event) => {
      const detail = (event as CustomEvent<Opened>).detail;
      setOpened(detail);
      setIndex(Math.max(0, detail.list.indexOf(detail.src)));
    };
    window.addEventListener(OPEN_EVENT, open);
    return () => window.removeEventListener(OPEN_EVENT, open);
  }, []);

  if (!opened) return null;
  const { list } = opened;
  const step = (by: number) => {
    const next = index + by;
    if (next < 0 || next >= list.length) return false;
    setIndex(next);
    return true;
  };
  return (
    <Viewer
      src={list[index]}
      closeLabel={closeLabel}
      onClose={() => setOpened(null)}
      onStep={list.length > 1 ? step : undefined}
    />
  );
}

function Viewer({
  src,
  closeLabel,
  onClose,
  onStep,
}: {
  src: string;
  closeLabel: string;
  onClose: () => void;
  /** To the next (1) or the previous (-1) picture; false at the list's end. */
  onStep?: (by: number) => boolean;
}) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState<Point>({ x: 0, y: 0 });
  const [moving, setMoving] = useState(false);
  const pointers = useRef(new Map<number, Point>());
  const pinch = useRef<{ distance: number; scale: number } | null>(null);
  const pan = useRef<{ start: Point; offset: Point } | null>(null);
  const lastTap = useRef(0);
  const tapTimer = useRef<number | null>(null);
  const moved = useRef(false);
  // A slide at the picture's own size: how far, while the finger is down.
  const [slide, setSlide] = useState(0);

  useBackHandler(true, onClose);

  useEffect(() => {
    setScale(1);
    setOffset({ x: 0, y: 0 });
    setSlide(0);
  }, [src]);

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
      if (onStep && Math.abs(dx) > Math.abs(dy)) setSlide(dx);
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
    const slid = slide;
    setSlide(0);
    if (onStep && scale <= 1.02 && Math.abs(slid) > SWIPE_PX) {
      onStep(slid < 0 ? 1 : -1);
      return;
    }
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
        style={{
          transform: `translate(${offset.x + slide}px, ${offset.y}px) scale(${scale})`,
        }}
      />
    </div>,
    document.body,
  );
}
