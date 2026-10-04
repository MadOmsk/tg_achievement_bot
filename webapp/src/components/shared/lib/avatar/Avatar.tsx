import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { fetchAvatarBlob, type MeResponse } from "../../../../api";
import { platformMark } from "../../../../i18n";
import { PlatformLogo } from "../platform/Platform";
import { useImgFade } from "../img-fade/useImgFade";
import "./Avatar.css";

const avatarUrls = new Map<number, string | null>();
const avatarPending = new Map<number, Promise<string | null>>();
// Bumped when a person's face changes: a fetch started before it is stale and
// must neither land in the cache nor reach the screen.
const generations = new Map<number, number>();

function loadTelegramAvatar(personId: number, initData: string): Promise<string | null> {
  if (avatarUrls.has(personId)) return Promise.resolve(avatarUrls.get(personId) ?? null);
  const inflight = avatarPending.get(personId);
  if (inflight) return inflight;
  const generation = generations.get(personId) ?? 0;
  const job = fetchAvatarBlob(initData, personId).then((blob: Blob | null) => {
    if ((generations.get(personId) ?? 0) !== generation) return null;
    avatarPending.delete(personId);
    if (!blob) {
      avatarUrls.set(personId, null);
      return null;
    }
    const url = URL.createObjectURL(blob);
    avatarUrls.set(personId, url);
    return url;
  });
  avatarPending.set(personId, job);
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

// A picture chosen in the app (#157) replaces the Telegram photo everywhere,
// one's own face included: then it is fetched by person_id like anybody else's.
let ownCustom = false;
let epoch = 0;
const epochListeners = new Set<() => void>();

export function setOwnAvatarCustom(custom: boolean): void {
  ownCustom = custom;
}

/** Forget a person's cached face, so every avatar of theirs on screen reloads. */
export function forgetAvatar(personId: number): void {
  const url = avatarUrls.get(personId);
  if (url) URL.revokeObjectURL(url);
  avatarUrls.delete(personId);
  avatarPending.delete(personId);
  generations.set(personId, (generations.get(personId) ?? 0) + 1);
  epoch += 1;
  epochListeners.forEach((listen) => listen());
}

export function telegramPhoto(): string | null {
  if (ownCustom) return null;
  return window.Telegram?.WebApp?.initDataUnsafe?.user?.photo_url ?? null;
}

export function accountLabel(me: MeResponse): string {
  return (
    me.handle?.display ||
    me.xbox.gamertag_modern ||
    me.xbox.gamertag ||
    me.username ||
    `id${me.person_id}`
  );
}

export function Avatar({
  name,
  photo,
  personId,
  playing,
  online,
  platform,
  size = 44,
  zoomLabel,
}: {
  name: string;
  photo?: string | null;
  personId?: number;
  playing?: boolean;
  online?: boolean;
  platform?: string | null;
  size?: number;
  /** Set (to the close label) to let a tap open the photo fullscreen. */
  zoomLabel?: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [zoomed, setZoomed] = useState(false);
  const [seen, setSeen] = useState(epoch);
  useEffect(() => {
    const listen = () => setSeen(epoch);
    epochListeners.add(listen);
    return () => {
      epochListeners.delete(listen);
    };
  }, []);
  const fade = useImgFade(src);
  useEffect(() => {
    let cancelled = false;
    const takeBlob = () => {
      if (personId == null) return;
      const data = window.Telegram?.WebApp?.initData ?? "";
      void loadTelegramAvatar(personId, data).then((url) => {
        if (!cancelled) setSrc(url);
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
  }, [photo, personId, seen]);
  const live = Boolean(online || playing);
  const plat = (live && platform) && platformMark(platform);
  const fillBadge = Boolean(plat);
  const logoSize = Math.max(9, Math.min(13, Math.round(size * 0.26)));
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
