import { useEffect, useRef, useState } from "react";
import { ApiError, userApi } from "../../api";
import { useApp } from "../../app/context";
import { formatWhen } from "../../i18n";
import { Button, Field, Group, Row } from "../../ui/Controls";
import { Face } from "../../ui/Face";
import { Icon } from "../../ui/Icon";
import { Confirm, Sheet } from "../../ui/Page";

const OUT = 512;

export function ProfilePane() {
  const { me, data, tr, setMe, toast, locale, open } = useApp();
  const [name, setName] = useState(me.handle?.name ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  const [picked, setPicked] = useState<string | null>(null);
  const [askReset, setAskReset] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const valid = /^[A-Za-z0-9]{3,20}$/.test(name);
  const changed = name !== (me.handle?.name ?? "");
  const next = me.handle?.next_change_at;
  const onlyCase = changed && name.toLowerCase() === (me.handle?.name ?? "").toLowerCase();

  const saveName = async () => {
    setBusy(true);
    setError(null);
    try {
      setMe(await userApi.putHandle(data, name));
      toast(tr("nicknameSaved"));
    } catch (err) {
      setError(err instanceof ApiError && err.code === "too_soon" ? tr("nicknameTooSoon") : tr("nicknameInvalid"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="pf-face">
        <Face personId={me.person_id} name={me.handle?.display ?? ""} size={128} version={version} />
        <div className="pf-face-actions">
          <Button variant="tonal" icon="image" onClick={() => file.current?.click()}>
            {tr("avatarChange")}
          </Button>
          {me.avatar_custom && me.tg_id != null && (
            <Button variant="text" onClick={() => setAskReset(true)}>
              {tr("avatarReset")}
            </Button>
          )}
        </div>
        <input
          ref={file}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) setPicked(URL.createObjectURL(f));
          }}
        />
      </div>

      <Group title={tr("nickname")}>
        <form
          className="set-pad set-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (valid && changed) void saveName();
          }}
        >
          <Field
            value={name}
            icon="user"
            maxLength={20}
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            onChange={(e) => setName(e.target.value.replace(/[^A-Za-z0-9]/g, ""))}
            error={error}
            hint={
              error
                ? null
                : next && !onlyCase
                  ? `${tr("nicknameNext")} ${formatWhen(next, locale)}`
                  : me.handle?.number
                    ? `${tr("nicknameHint")} ${tr("nicknameDigits")} ${me.handle.display}`
                    : tr("nicknameHint")
            }
          />
          {changed && (
            <Button type="submit" busy={busy} disabled={!valid}>
              {tr("nicknameSave")}
            </Button>
          )}
        </form>
      </Group>
      <Group>
        <Row lead={<Icon name="user" />} title={tr("profileOpenCard")} chevron onClick={() => open({ kind: "person", personId: me.person_id })} />
      </Group>

      {picked && (
        <Cropper
          src={picked}
          onCancel={() => {
            URL.revokeObjectURL(picked);
            setPicked(null);
          }}
          onDone={async (blob) => {
            URL.revokeObjectURL(picked);
            setPicked(null);
            try {
              setMe(await userApi.putAvatar(data, blob));
              setVersion(Date.now());
              toast(tr("avatarDone"));
            } catch {
              toast(tr("avatarFailed"), "error");
            }
          }}
        />
      )}
      {askReset && (
        <Confirm
          text={tr("avatarResetConfirm")}
          yes={tr("avatarReset")}
          no={tr("cancel")}
          onYes={async () => {
            setAskReset(false);
            try {
              setMe(await userApi.deleteAvatar(data));
              setVersion(Date.now());
            } catch {
              toast(tr("somethingWrong"), "error");
            }
          }}
          onNo={() => setAskReset(false)}
        />
      )}
    </>
  );
}

/** Move and zoom the picture inside a square, then keep that square as a
 * 512 px JPEG (the server decodes and saves it again on its side). */
function Cropper({ src, onCancel, onDone }: { src: string; onCancel: () => void; onDone: (blob: Blob) => void }) {
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
    <Sheet title={tr("avatarPlace")} onClose={onCancel} layer="crop">
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
          <span className="crop-mask shape-cookie12" />
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
