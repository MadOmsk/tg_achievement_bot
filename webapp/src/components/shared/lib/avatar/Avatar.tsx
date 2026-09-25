import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { fetchAvatarBlob, type MeResponse } from "../../../../api";
import { platformMark } from "../../../../i18n";
import { PlatformLogo } from "../platform/Platform";
import { useImgFade } from "../img-fade/useImgFade";
import "./Avatar.css";

const avatarUrls = new Map<number, string | null>();
const avatarPending = new Map<number, Promise<string | null>>();

function loadTelegramAvatar(tgId: number, initData: string): Promise<string | null> {
  if (avatarUrls.has(tgId)) return Promise.resolve(avatarUrls.get(tgId) ?? null);
  const inflight = avatarPending.get(tgId);
  if (inflight) return inflight;
  const job = fetchAvatarBlob(initData, tgId).then((blob: Blob | null) => {
    avatarPending.delete(tgId);
    if (!blob) {
      avatarUrls.set(tgId, null);
      return null;
    }
    const url = URL.createObjectURL(blob);
    avatarUrls.set(tgId, url);
    return url;
  });
  avatarPending.set(tgId, job);
  return job;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export function isOnline(row: { state?: string | null; playing?: boolean }): boolean {
  return Boolean(row.playing || row.state === "Online" || row.state === "online");
}

export function telegramPhoto(): string | null {
  return window.Telegram?.WebApp?.initDataUnsafe?.user?.photo_url ?? null;
}

export function accountLabel(me: MeResponse): string {
  return (
    me.xbox.gamertag_modern ||
    me.xbox.gamertag ||
    [me.first_name, me.last_name].filter(Boolean).join(" ") ||
    me.username ||
    `id${me.tg_id}`
  );
}

export function Avatar({
  name,
  photo,
  tgId,
  playing,
  online,
  platform,
  size = 44,
  zoomLabel,
}: {
  name: string;
  photo?: string | null;
  tgId?: number;
  playing?: boolean;
  online?: boolean;
  platform?: string | null;
  size?: number;
  /** Set (to the close label) to let a tap open the photo fullscreen. */
  zoomLabel?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const fade = useImgFade(src);
  useEffect(() => {
    let cancelled = false;
    const takeBlob = () => {
      if (tgId == null) return;
      const data = window.Telegram?.WebApp?.initData ?? "";
      void loadTelegramAvatar(tgId, data).then((url) => {
        if (!cancelled && url) setSrc(url);
      });
    };
    if (photo) {
      const url = photo.trim();
      if (!url) {
        setSrc(null);
        takeBlob();
        return () => {
          cancelled = true;
        };
      }
      const probe = new Image();
      probe.onload = () => {
        if (!cancelled) setSrc(url);
      };
      probe.onerror = () => {
        if (cancelled) return;
        setSrc(null);
        takeBlob();
      };
      probe.src = url;
      return () => {
        cancelled = true;
        probe.onload = null;
        probe.onerror = null;
        probe.src = "";
      };
    }
    setSrc(null);
    takeBlob();
    return () => {
      cancelled = true;
    };
  }, [photo, tgId]);
  const live = Boolean(online || playing);
  const plat = (live && platform) && platformMark(platform);
  const fillBadge = plat === "steam" || plat === "xbox";
  const logoSize = fillBadge
    ? Math.max(12, Math.min(18, Math.round(size * 0.34)))
    : Math.max(7, Math.min(11, Math.round(size * 0.18)));
  return (
    <span className={live ? "avatar-wrap is-live" : "avatar-wrap"} style={{ width: size, height: size }}>
      <span
        className={src && zoomLabel ? "avatar is-zoomable" : "avatar"}
        role={src && zoomLabel ? "button" : undefined}
        onClick={
          src && zoomLabel
            ? (e) => {
                e.stopPropagation();
                setZoomed(true);
              }
            : undefined
        }
      >
        {src ? (
          <img
            ref={fade.ref}
            src={src}
            alt=""
            className={fade.className}
            draggable={false}
            onLoad={fade.onLoad}
          />
        ) : (
          <span>{initials(name)}</span>
        )}
      </span>
      {(zoomed && src && zoomLabel) &&
        createPortal(
          <button
            type="button"
            className="avatar-zoom"
            aria-label={zoomLabel}
            onClick={(e) => {
              // A portal bubbles through the React tree: keep the tap that
              // closes the photo from reaching whatever wraps the avatar.
              e.stopPropagation();
              setZoomed(false);
            }}
          >
            <img src={src} alt="" draggable={false} />
          </button>,
          document.body,
        )}
      {live && (
        <span
          className={
            plat
              ? fillBadge
                ? "avatar-dot has-plat is-fill"
                : "avatar-dot has-plat"
              : "avatar-dot"
          }
        >
          {plat && <PlatformLogo platform={plat} size={logoSize} />}
        </span>
      )}
    </span>
  );
}
