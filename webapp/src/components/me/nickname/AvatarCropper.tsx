import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { t, type Locale } from "../../../i18n";
import "./AvatarCropper.css";

const VIEW = 280;
const OUT = 512;
const MAX_ZOOM = 4;

/** Place a picture in the avatar's circle before it is uploaded: drag to move,
 * pinch, the wheel or the slider to zoom. The circle is always covered. */
export function AvatarCropper({
  file,
  locale,
  onCancel,
  onDone,
}: {
  file: File;
  locale: Locale;
  onCancel: () => void;
  onDone: (image: Blob) => void;
}) {
  const [img, setImg] = useState<HTMLImageElement | null>(null);
  const [url, setUrl] = useState("");
  const [zoom, setZoom] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ dist: number; zoom: number } | null>(null);

  // The parent's handler changes every render; the picture loads once per file.
  const cancel = useRef(onCancel);
  cancel.current = onCancel;
  useEffect(() => {
    const src = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => setImg(image);
    image.onerror = () => cancel.current();
    image.src = src;
    setUrl(src);
    return () => {
      // A revoked URL fails to load: a cleaned-up attempt must not cancel the editor.
      image.onload = null;
      image.onerror = null;
      URL.revokeObjectURL(src);
    };
  }, [file]);

  useEffect(() => {
    const html = document.documentElement;
    html.classList.add("is-sheet-open");
    return () => html.classList.remove("is-sheet-open");
  }, []);

  const cover = img ? VIEW / Math.min(img.naturalWidth, img.naturalHeight) : 1;
  const width = img ? img.naturalWidth * cover * zoom : VIEW;
  const height = img ? img.naturalHeight * cover * zoom : VIEW;

  // Keep the picture over the whole circle: never a gap at an edge.
  const clamp = (p: { x: number; y: number }, w = width, h = height) => ({
    x: Math.max(-(w - VIEW) / 2, Math.min((w - VIEW) / 2, p.x)),
    y: Math.max(-(h - VIEW) / 2, Math.min((h - VIEW) / 2, p.y)),
  });

  const setZoomKeeping = (next: number) => {
    const z = Math.max(1, Math.min(MAX_ZOOM, next));
    const ratio = z / zoom;
    const w = img ? img.naturalWidth * cover * z : VIEW;
    const h = img ? img.naturalHeight * cover * z : VIEW;
    setZoom(z);
    setPos((p) => clamp({ x: p.x * ratio, y: p.y * ratio }, w, h));
  };

  const onDown = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture?.(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      pinch.current = { dist: Math.hypot(a.x - b.x, a.y - b.y), zoom };
    }
  };
  const onMove = (e: React.PointerEvent) => {
    const prev = pointers.current.get(e.pointerId);
    if (!prev) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size >= 2 && pinch.current) {
      const [a, b] = [...pointers.current.values()];
      setZoomKeeping((pinch.current.zoom * Math.hypot(a.x - b.x, a.y - b.y)) / pinch.current.dist);
      return;
    }
    setPos((p) => clamp({ x: p.x + e.clientX - prev.x, y: p.y + e.clientY - prev.y }));
  };
  const onUp = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
  };

  const save = () => {
    if (!img) return;
    const left = VIEW / 2 - width / 2 + pos.x;
    const top = VIEW / 2 - height / 2 + pos.y;
    const scale = cover * zoom;
    const canvas = document.createElement("canvas");
    canvas.width = OUT;
    canvas.height = OUT;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(img, -left / scale, -top / scale, VIEW / scale, VIEW / scale, 0, 0, OUT, OUT);
    canvas.toBlob((blob) => blob && onDone(blob), "image/jpeg", 0.88);
  };

  return createPortal(
    <div className="crop-layer">
      <p className="crop-title">{t(locale, "avatarPlace")}</p>
      <div
        className="crop-view"
        style={{ width: VIEW, height: VIEW }}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
        onWheel={(e) => setZoomKeeping(zoom * (e.deltaY < 0 ? 1.08 : 1 / 1.08))}
      >
        {img && (
          <img
            src={url}
            alt=""
            draggable={false}
            style={{
              width,
              height,
              transform: `translate(${pos.x - (width - VIEW) / 2}px, ${pos.y - (height - VIEW) / 2}px)`,
            }}
          />
        )}
        <span className="crop-ring" aria-hidden />
      </div>
      <input
        className="crop-zoom"
        type="range"
        min={1}
        max={MAX_ZOOM}
        step={0.01}
        value={zoom}
        onChange={(e) => setZoomKeeping(Number(e.target.value))}
        aria-label={t(locale, "avatarZoom")}
      />
      <div className="crop-actions">
        <button type="button" className="btn is-quiet" onClick={onCancel}>
          {t(locale, "cancel")}
        </button>
        <button type="button" className="btn" onClick={save} disabled={!img}>
          {t(locale, "save")}
        </button>
      </div>
    </div>,
    document.body,
  );
}
