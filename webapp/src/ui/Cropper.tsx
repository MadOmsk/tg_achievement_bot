import { useEffect, useRef, useState } from "react";
import { useApp } from "../app/context";
import { Button } from "./Controls";
import { Sheet } from "./Page";

/** Move and zoom a picture inside a square, then keep that square as a JPEG
 * of `size` px (the server decodes and saves it again on its side). `round`
 * shows the circle a face is cut to; else the square with its corners. */
export function Cropper({
  src,
  title,
  size: OUT = 512,
  round = false,
  onCancel,
  onDone,
}: {
  src: string;
  title: string;
  size?: number;
  round?: boolean;
  onCancel: () => void;
  onDone: (blob: Blob) => void;
}) {
  const { tr } = useApp();
  const box = useRef<HTMLDivElement>(null);
  const img = useRef<HTMLImageElement>(null);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const [size, setSize] = useState(300);

  useEffect(() => {
    if (box.current) setSize(box.current.clientWidth);
  }, []);

  const base = natural ? size / Math.min(natural.w, natural.h) : 1;
  const scale = base * zoom;
  const w = (natural?.w ?? 0) * scale;
  const h = (natural?.h ?? 0) * scale;
  const clamp = (p: { x: number; y: number }) => ({
    x: Math.min(0, Math.max(size - w, p.x)),
    y: Math.min(0, Math.max(size - h, p.y)),
  });

  useEffect(() => {
    if (!natural) return;
    setPos((p) => clamp(p.x === 0 && p.y === 0 ? { x: (size - w) / 2, y: (size - h) / 2 } : p));
  }, [natural, zoom, size]);

  const save = () => {
    if (!img.current || !natural) return;
    const canvas = document.createElement("canvas");
    canvas.width = OUT;
    canvas.height = OUT;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const k = OUT / size;
    ctx.drawImage(img.current, pos.x * k, pos.y * k, w * k, h * k);
    canvas.toBlob((blob) => blob && onDone(blob), "image/jpeg", 0.9);
  };

  return (
    <Sheet title={title} onClose={onCancel} layer="crop">
      <div className="crop">
        <div
          className="crop-box"
          ref={box}
          onPointerDown={(e) => {
            (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
            drag.current = { x: e.clientX, y: e.clientY, px: pos.x, py: pos.y };
          }}
          onPointerMove={(e) => {
            const d = drag.current;
            if (d) setPos(clamp({ x: d.px + e.clientX - d.x, y: d.py + e.clientY - d.y }));
          }}
          onPointerUp={() => (drag.current = null)}
        >
          <img
            ref={img}
            src={src}
            alt=""
            draggable={false}
            onLoad={(e) => setNatural({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
            style={{ width: w || undefined, height: h || undefined, transform: `translate(${pos.x}px, ${pos.y}px)` }}
          />
          <span className={`crop-mask${round ? "" : " crop-mask-square"}`} />
        </div>
        <label className="crop-zoom">
          <span>{tr("avatarZoom")}</span>
          <input type="range" min={1} max={3} step={0.01} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} />
        </label>
        <div className="crop-actions">
          <Button variant="text" onClick={onCancel}>
            {tr("cancel")}
          </Button>
          <Button onClick={save} disabled={!natural}>
            {tr("save")}
          </Button>
        </div>
      </div>
    </Sheet>
  );
}
