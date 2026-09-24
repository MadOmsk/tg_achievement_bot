import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { fetchAvatarBlob, type MeResponse } from "./api";
import { platformLabel, platformMark, t, type Locale } from "./i18n";

const avatarUrls = new Map<number, string | null>();
const avatarPending = new Map<number, Promise<string | null>>();

function loadTelegramAvatar(tgId: number, initData: string): Promise<string | null> {
  if (avatarUrls.has(tgId)) return Promise.resolve(avatarUrls.get(tgId) ?? null);
  const inflight = avatarPending.get(tgId);
  if (inflight) return inflight;
  const job = fetchAvatarBlob(initData, tgId).then((blob) => {
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

/** Game cover or achievement icon — gradient + glyph when URL is missing or 404.
 *  Preload off-DOM so a dead CDN never flashes the browser's broken-image icon
 *  (Telegram's WebView often keeps that glyph even after onError). */
const coverReady = new Map<string, boolean>();

export function CoverImg({
  src,
  kind = "game",
  className,
  imgClassName,
  children,
}: {
  src?: string | null;
  kind?: "game" | "achievement";
  className?: string;
  imgClassName?: string;
  children?: ReactNode;
}) {
  const url = (src ?? "").trim();
  const [ready, setReady] = useState<string | null>(() =>
    url && coverReady.get(url) ? url : null,
  );
  useEffect(() => {
    if (!url) {
      setReady(null);
      return;
    }
    if (coverReady.get(url)) {
      setReady(url);
      return;
    }
    let cancelled = false;
    // Keep the last good frame if the same URL is already showing — a hard
    // clear flashes the empty glyph when a carousel clones a slide.
    setReady((prev) => (prev === url ? prev : null));
    const probe = new Image();
    probe.onload = () => {
      coverReady.set(url, true);
      if (!cancelled) setReady(url);
    };
    probe.onerror = () => {
      coverReady.set(url, false);
      if (!cancelled) setReady(null);
    };
    probe.src = url;
    return () => {
      cancelled = true;
      probe.onload = null;
      probe.onerror = null;
      probe.src = "";
    };
  }, [url]);
  const ok = ready != null;
  const hero = Boolean(className?.includes("profile-hero-art"));
  const gameHero = Boolean(className?.includes("game-card-art"));
  const markSize = hero ? 96 : gameHero ? 112 : 28;
  return (
    <span
      className={["cover-ph", `is-${kind}`, ok ? "has-img" : "is-empty", className]
        .filter(Boolean)
        .join(" ")}
    >
      {ok ? (
        <img src={ready} alt="" className={imgClassName} draggable={false} />
      ) : (
        <span className="cover-ph-mark" aria-hidden>
          {kind === "achievement" ? (
            <Icon name="cup" size={markSize} filled />
          ) : (
            <GamePadMark size={markSize} />
          )}
        </span>
      )}
      {children}
    </span>
  );
}

function GamePadMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.55"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M7.4 8.6h9.2a4.4 4.4 0 0 1 4.2 5.6l-.6 2.2a2.9 2.9 0 0 1-2.8 2.1H6.6a2.9 2.9 0 0 1-2.8-2.1l-.6-2.2a4.4 4.4 0 0 1 4.2-5.6Z" />
      <path d="M9 12.1v3.1M7.45 13.65h3.1" />
      <circle cx="15.15" cy="12.35" r="0.85" fill="currentColor" stroke="none" />
      <circle cx="17.2" cy="14.25" r="0.85" fill="currentColor" stroke="none" />
    </svg>
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
}: {
  name: string;
  photo?: string | null;
  tgId?: number;
  playing?: boolean;
  online?: boolean;
  platform?: string | null;
  size?: number;
}) {
  const [src, setSrc] = useState<string | null>(null);
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
  const plat = live && platform ? platformMark(platform) : null;
  // Steam/Xbox marks are round — fill the green badge. PSN stays inset.
  const fillBadge = plat === "steam" || plat === "xbox";
  const logoSize = fillBadge
    ? Math.max(12, Math.min(18, Math.round(size * 0.34)))
    : Math.max(7, Math.min(11, Math.round(size * 0.18)));
  return (
    <span className={live ? "avatar-wrap is-live" : "avatar-wrap"} style={{ width: size, height: size }}>
      <span className="avatar">
        {src ? <img src={src} alt="" draggable={false} /> : <span>{initials(name)}</span>}
      </span>
      {live ? (
        <span
          className={
            plat
              ? fillBadge
                ? "avatar-dot has-plat is-fill"
                : "avatar-dot has-plat"
              : "avatar-dot"
          }
        >
          {plat ? <PlatformLogo platform={plat} size={logoSize} /> : null}
        </span>
      ) : null}
    </span>
  );
}

export function Icon({
  name,
  size = 24,
  filled = false,
}: {
  name:
    | "home"
    | "people"
    | "search"
    | "gear"
    | "g"
    | "feed"
    | "lock"
    | "stats"
    | "cup"
    | "back"
    | "forward"
    | "link"
    | "sync"
    | "off";
  size?: number;
  filled?: boolean;
}) {
  const props = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: filled ? "currentColor" : "none",
    stroke: filled ? "none" : "currentColor",
    strokeWidth: filled ? 0 : 1.75,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (name === "home") {
    return (
      <svg {...props}>
        <path d="M4 10.5 12 4l8 6.5V20a1.2 1.2 0 0 1-1.2 1.2h-4.6v-6.2H9.8v6.2H5.2A1.2 1.2 0 0 1 4 20z" />
      </svg>
    );
  }
  if (name === "people") {
    if (filled) {
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <circle cx="9" cy="8" r="3.15" />
          <path d="M3.1 20.2c0-3.4 2.6-5.8 5.9-5.8s5.9 2.4 5.9 5.8V21H3.1z" />
          <circle cx="16.7" cy="9.1" r="2.45" />
          <path d="M13.2 20.2c.5-1.7 1.6-3.1 3.4-3.8 1.8.7 3 2.1 3.5 3.8V21h-6.9z" />
        </svg>
      );
    }
    return (
      <svg {...props}>
        <circle cx="9" cy="8" r="3" />
        <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
        <circle cx="17" cy="9" r="2.4" />
        <path d="M16 19a4.5 4.5 0 0 1 5-4.4" />
      </svg>
    );
  }
  if (name === "stats") {
    return (
      <svg {...props}>
        <rect x="4" y="11" width="3.2" height="8" rx="1" />
        <rect x="10.4" y="5" width="3.2" height="14" rx="1" />
        <rect x="16.8" y="9" width="3.2" height="10" rx="1" />
      </svg>
    );
  }
  if (name === "search") {
    return (
      <svg {...props}>
        {filled ? (
          <>
            <circle cx="11" cy="11" r="7" />
            <path d="m16.2 16.2 5 5" stroke="currentColor" strokeWidth="2.2" fill="none" />
          </>
        ) : (
          <>
            <circle cx="11" cy="11" r="6.5" />
            <path d="m16 16 4 4" />
          </>
        )}
      </svg>
    );
  }
  if (name === "feed") {
    return (
      <svg {...props}>
        <rect x="3.5" y="4.5" width="17" height="5" rx="1.6" />
        <rect x="3.5" y="11.5" width="17" height="5" rx="1.6" />
        <rect x="3.5" y="18.5" width="11" height="2.2" rx="1" />
      </svg>
    );
  }
  if (name === "lock") {
    return (
      <svg {...props}>
        <rect x="5" y="11" width="14" height="10" rx="2" />
        <path d="M8 11V8a4 4 0 0 1 8 0v3" />
      </svg>
    );
  }
  if (name === "gear") {
    return (
      <svg {...props}>
        <path d="M12 8.4a3.6 3.6 0 1 0 0 7.2 3.6 3.6 0 0 0 0-7.2z" />
        <path d="M19.2 13.1c.05-.36.08-.73.08-1.1s-.03-.74-.08-1.1l2.05-1.6-1.95-3.38-2.42.78a7.7 7.7 0 0 0-1.9-1.1L14.6 3.5h-5.2l-.38 2.1a7.7 7.7 0 0 0-1.9 1.1l-2.42-.78-1.95 3.38 2.05 1.6a7.4 7.4 0 0 0 0 2.2l-2.05 1.6 1.95 3.38 2.42-.78c.57.45 1.2.82 1.9 1.1l.38 2.1h5.2l.38-2.1c.7-.28 1.33-.65 1.9-1.1l2.42.78 1.95-3.38z" />
      </svg>
    );
  }
  if (name === "back") {
    return (
      <svg {...props} strokeWidth={filled ? 0 : 2.35}>
        <path d="M14.2 5.2 7.2 12l7 6.8" />
        <path d="M8.1 12h9.7" />
      </svg>
    );
  }
  if (name === "forward") {
    return (
      <svg {...props} strokeWidth={filled ? 0 : 2.35}>
        <path d="M9.8 5.2 16.8 12l-7 6.8" />
        <path d="M6.2 12h9.7" />
      </svg>
    );
  }
  if (name === "cup") {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="currentColor"
        aria-hidden
      >
        <path d="M31.734,2.429c-1.438-1.196-3.664-1.953-6.543,0.354c-0.006-0.35-0.01-0.695-0.022-1.059c-1.79,0-16.547,0-18.337,0 C6.818,2.088,6.814,2.434,6.81,2.782C3.93,0.477,1.705,1.231,0.268,2.43L0,2.653l0.017,0.346c0.015,0.333,0.432,8.199,4.749,11.769 c1.508,1.247,3.305,1.824,5.343,1.701c-0.139,0.438-0.414,1.042-0.731,1.574l1.197,0.718c0.227-0.379,0.602-1.066,0.828-1.769 c1.59,1.29,2.982,1.677,2.982,2.631c0,2.148-5.313,3.546-5.504,4.891H8.143v0.567H7.355v5.632h17.116v-5.632h-0.691v-0.567H23.12 c-0.188-1.345-5.505-2.741-5.505-4.891c0-0.955,1.393-1.342,2.984-2.631c0.227,0.701,0.601,1.389,0.825,1.768l1.199-0.719 c-0.317-0.53-0.595-1.135-0.731-1.572c2.039,0.122,3.834-0.454,5.342-1.701c4.317-3.57,4.733-11.437,4.75-11.77L32,2.65 L31.734,2.429z M5.659,13.694C2.301,10.919,1.57,4.828,1.438,3.291c1.586-1.121,3.353-0.673,5.378,1.364 C6.824,4.919,6.84,5.169,6.854,5.422c-0.49,0.47-1.151,1.085-1.756,1.633l0.938,1.036c0.36-0.326,0.676-0.613,0.952-0.868 c0.409,3.825,1.438,6.242,2.604,7.855C8.095,15.075,6.773,14.615,5.659,13.694z M21.936,29.541H10.219v-2.863h11.716V29.541z M26.342,13.694c-1.113,0.921-2.436,1.38-3.932,1.384c1.165-1.614,2.195-4.03,2.604-7.854c0.277,0.254,0.592,0.541,0.953,0.867 l0.938-1.035c-0.605-0.548-1.268-1.162-1.756-1.635c0.014-0.252,0.027-0.501,0.035-0.766c2.025-2.037,3.793-2.485,5.379-1.365 C30.43,4.827,29.701,10.918,26.342,13.694z" />
      </svg>
    );
  }
  if (name === "link") {
    return (
      <svg {...props}>
        <path d="M10 14a4.5 4.5 0 0 0 6.36.2l2.2-2.2a4.5 4.5 0 0 0-6.36-6.36l-1.1 1.1" />
        <path d="M14 10a4.5 4.5 0 0 0-6.36-.2l-2.2 2.2a4.5 4.5 0 0 0 6.36 6.36l1.1-1.1" />
      </svg>
    );
  }
  if (name === "sync") {
    return (
      <svg {...props}>
        <path d="M20 12a8 8 0 0 1-13.5 5.8" />
        <path d="M4 12a8 8 0 0 1 13.5-5.8" />
        <path d="M16.5 3.5V6.8H20" />
        <path d="M7.5 20.5V17.2H4" />
      </svg>
    );
  }
  if (name === "off") {
    return (
      <svg {...props}>
        <path d="M12 3.5v8" />
        <path d="M7.2 6.4a7 7 0 1 0 9.6 0" />
      </svg>
    );
  }
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <circle cx="12" cy="12" r="10" fill="#3ee0a0" />
      <text
        x="12"
        y="16.2"
        textAnchor="middle"
        fontSize="13"
        fontWeight="700"
        fill="#0a0c12"
        fontFamily="inherit"
      >
        G
      </text>
    </svg>
  );
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

export function Chip({
  mark,
  children,
}: {
  mark?: string;
  children: ReactNode;
}) {
  return (
    <span className="chip">
      {mark ? <span className={`mark ${mark}`} /> : null}
      {children}
    </span>
  );
}

export function PlatformChip({ platform, locale }: { platform: string; locale: Locale }) {
  return <Chip mark={platformMark(platform)}>{platformLabel(platform, locale)}</Chip>;
}

export function PlatformLogo({
  platform,
  size = 16,
}: {
  platform: string;
  size?: number;
}) {
  const kind = platformMark(platform);
  const svg = {
    className: "plat-logo-svg",
    "aria-hidden": true,
  };
  return (
    <span className={`plat-logo is-${kind}`} style={{ width: size, height: size }} aria-hidden>
      {kind === "steam" ? (
        <svg {...svg} viewBox="0 0 32 32">
          <path d="M18.102 12.129c0-0 0-0 0-0.001 0-1.564 1.268-2.831 2.831-2.831s2.831 1.268 2.831 2.831c0 1.564-1.267 2.831-2.831 2.831-0 0-0 0-0.001 0h0c-0 0-0 0-0.001 0-1.563 0-2.83-1.267-2.83-2.83 0-0 0-0 0-0.001v0zM24.691 12.135c0-2.081-1.687-3.768-3.768-3.768s-3.768 1.687-3.768 3.768c0 2.081 1.687 3.768 3.768 3.768v0c2.080-0.003 3.765-1.688 3.768-3.767v-0zM10.427 23.76l-1.841-0.762c0.524 1.078 1.611 1.808 2.868 1.808 1.317 0 2.448-0.801 2.93-1.943l0.008-0.021c0.155-0.362 0.246-0.784 0.246-1.226 0-1.757-1.424-3.181-3.181-3.181-0.405 0-0.792 0.076-1.148 0.213l0.022-0.007 1.903 0.787c0.852 0.364 1.439 1.196 1.439 2.164 0 1.296-1.051 2.347-2.347 2.347-0.324 0-0.632-0.066-0.913-0.184l0.015 0.006zM15.974 1.004c-7.857 0.001-14.301 6.046-14.938 13.738l-0.004 0.054 8.038 3.322c0.668-0.462 1.495-0.737 2.387-0.737 0.001 0 0.002 0 0.002 0h-0c0.079 0 0.156 0.005 0.235 0.008l3.575-5.176v-0.074c0.003-3.12 2.533-5.648 5.653-5.648 3.122 0 5.653 2.531 5.653 5.653s-2.531 5.653-5.653 5.653h-0.131l-5.094 3.638c0 0.065 0.005 0.131 0.005 0.199 0 0.001 0 0.002 0 0.003 0 2.342-1.899 4.241-4.241 4.241-2.047 0-3.756-1.451-4.153-3.38l-0.005-0.027-5.755-2.383c1.841 6.345 7.601 10.905 14.425 10.905 8.281 0 14.994-6.713 14.994-14.994s-6.713-14.994-14.994-14.994c-0 0-0.001 0-0.001 0h0z" />
        </svg>
      ) : kind === "psn" ? (
        <svg {...svg} viewBox="0 0 200 154.81912" preserveAspectRatio="xMidYMid meet">
        <path
          fillRule="evenodd"
          d="m 197.23914,117.96194 c -3.8677,4.8796 -13.34356,8.36053 -13.34356,8.36053 0,0 -70.49109,25.31994 -70.49109,25.31994 0,0 0,-18.67289 0,-18.67289 0,0 51.87665,-18.48401 51.87665,-18.48401 5.887,-2.10924 6.79096,-5.09097 2.00581,-6.65604 -4.77616,-1.56957 -13.42451,-1.11983 -19.31601,0.99841 0,0 -34.56645,12.17426 -34.56645,12.17426 0,0 0,-19.37898 0,-19.37898 0,0 1.99232,-0.6746 1.99232,-0.6746 0,0 9.98856,-3.534896 24.03371,-5.09097 14.04515,-1.547081 31.24291,0.211374 44.74389,5.32933 15.21445,4.80764 16.92793,11.89543 13.06473,16.77502 z M 120.11451,86.165853 c 0,0 0,-47.752601 0,-47.752601 0,-5.608163 -1.03439,-10.771093 -6.29626,-12.232725 -4.0296,-1.290734 -6.53012,2.45104 -6.53012,8.054706 0,0 0,119.583887 0,119.583887 0,0 -32.250314,-10.23591 -32.250314,-10.23591 0,0 0,-142.58321 0,-142.58321 13.712343,2.54549 33.689454,8.56291 44.429074,12.18326 27.31226,9.376917 36.57225,21.047482 36.57225,47.343343 0,25.630256 -15.82159,35.344478 -35.92463,25.63925 z M 15.862004,131.01768 C 0.24279269,126.6193 -2.3566614,117.45375 4.7626047,112.17389 c 6.5795883,-4.8751 17.7689333,-8.54492 17.7689333,-8.54492 0,0 46.241498,-16.442224 46.241498,-16.442224 0,0 0,18.744854 0,18.744854 0,0 -33.275709,11.90892 -33.275709,11.90892 -5.878004,2.10924 -6.781967,5.09547 -2.005807,6.66054 4.780657,1.56506 13.433512,1.11983 19.320511,-0.99391 0,0 15.961005,-5.79256 15.961005,-5.79256 0,0 0,16.77053 0,16.77053 -1.011893,0.17989 -2.140724,0.35978 -3.184104,0.53518 -15.965505,2.60845 -32.969893,1.5201 -49.726928,-4.00262 z m 171.105246,7.42508 c 2.0193,0 3.91267,0.78254 5.33832,2.22618 1.42566,1.42115 2.21269,3.31903 2.21269,5.33383 0,2.02379 -0.78703,3.91267 -2.21269,5.33383 -1.42565,1.43464 -3.31902,2.21718 -5.33832,2.21718 -2.0193,0 -3.90818,-0.78254 -5.33833,-2.21718 -1.42565,-1.42116 -2.20818,-3.31004 -2.20818,-5.33383 0,-4.16453 3.38198,-7.56001 7.54651,-7.56001 z m -6.27827,7.56001 c 0,1.6775 0.65211,3.25606 1.83941,4.43436 1.18279,1.19629 2.76585,1.8439 4.43886,1.8439 3.46743,0 6.27826,-2.81532 6.27826,-6.27826 0,-1.682 -0.64761,-3.26056 -1.8394,-4.44336 -1.1828,-1.19629 -2.76586,-1.83941 -4.43886,-1.83941 -1.67301,0 -3.25607,0.64312 -4.43886,1.83941 -1.1873,1.1828 -1.83941,2.76136 -1.83941,4.44336 z m 8.55841,-4.07008 c 0.82751,0.36428 1.24576,1.06586 1.24576,2.06427 0,0.5127 -0.10794,0.94444 -0.3283,1.28174 -0.15741,0.24285 -0.38228,0.44074 -0.63413,0.61163 0.19788,0.11694 0.37328,0.25635 0.50371,0.41826 0.17988,0.23386 0.28332,0.60713 0.29682,1.11533 0,0 0.0405,1.07486 0.0405,1.07486 0.0135,0.28783 0.0315,0.5082 0.0765,0.64312 0.045,0.19788 0.13042,0.32381 0.23835,0.36429 0,0 0.11244,0.054 0.11244,0.054 0,0 0,0.12143 0,0.12143 0,0 0,0.18439 0,0.18439 0,0 0,0.18439 0,0.18439 0,0 -0.18439,0 -0.18439,0 0,0 -1.33571,0 -1.33571,0 0,0 -0.10793,0 -0.10793,0 0,0 -0.054,-0.0944 -0.054,-0.0944 -0.045,-0.0899 -0.0764,-0.19338 -0.10793,-0.3283 -0.0225,-0.12143 -0.045,-0.3328 -0.0585,-0.65661 0,0 -0.0675,-1.33571 -0.0675,-1.33571 -0.018,-0.46322 -0.1754,-0.75105 -0.47222,-0.90396 -0.18439,-0.0854 -0.49021,-0.12592 -0.90396,-0.12592 0,0 -2.28914,0 -2.28914,0 0,0 0,3.26056 0,3.26056 0,0 0,0.18439 0,0.18439 0,0 -0.18889,0 -0.18889,0 0,0 -1.08836,0 -1.08836,0 0,0 -0.18438,0 -0.18438,0 0,0 0,-0.18439 0,-0.18439 0,0 0,-8.03672 0,-8.03672 0,0 0,-0.18439 0,-0.18439 0,0 0.18438,0 0.18438,0 0,0 3.71929,0 3.71929,0 0.63863,0 1.17381,0.0944 1.58756,0.28782 z m -4.0296,3.38648 c 0,0 2.32961,0 2.32961,0 0.46772,0 0.841,-0.0855 1.10634,-0.26084 0.24286,-0.1754 0.35979,-0.49471 0.35979,-0.95793 0,-0.5037 -0.1664,-0.83201 -0.51719,-1.0074 -0.19338,-0.0944 -0.46323,-0.14841 -0.80503,-0.14841 0,0 -2.47352,0 -2.47352,0 0,0 0,2.37458 0,2.37458 z"
        />
        </svg>
      ) : (
        <svg {...svg} viewBox="0 0 372.36823 372.57281">
          <g transform="translate(-1.5706619,12.357467)">
            <path d="M 169.18811,359.44924 C 140.50497,356.70211 111.4651,346.40125 86.518706,330.1252 65.614374,316.48637 60.893704,310.87967 60.893704,299.69061 c 0,-22.47524 24.711915,-61.84014 66.992496,-106.71584 24.01246,-25.48631 57.46022,-55.36001 61.0775,-54.55105 7.0309,1.57238 63.25048,56.41053 84.29655,82.2252 33.28077,40.82148 48.58095,74.24535 40.808,89.14682 -5.9087,11.32753 -42.57224,33.4669 -69.50775,41.97242 -22.19984,7.01011 -51.35538,9.9813 -75.37239,7.68108 z M 32.660004,276.3228 C 15.288964,249.67326 6.5125436,223.43712 2.2752336,185.49086 c -1.39917002,-12.53 -0.89778,-19.69701 3.17715,-45.41515 5.0788204,-32.05404 23.3330104,-69.136381 45.2671304,-91.957616 9.34191,-9.719732 10.17624,-9.956543 21.56341,-6.120482 13.828357,4.658436 28.595936,14.857457 51.498366,35.56661 l 13.36254,12.082873 -7.2969,8.96431 C 95.97448,140.22403 60.217254,199.2085 46.741444,235.70071 c -7.32599,19.83862 -10.28084,39.75281 -7.12868,48.04363 2.12818,5.59752 0.17339,3.51093 -6.95276,-7.42154 z m 304.915426,4.53255 c 1.71605,-8.37719 -0.4544,-23.76257 -5.5413,-39.28002 -11.01667,-33.60598 -47.83964,-96.12421 -81.65282,-138.63054 L 239.73699,89.563875 251.25285,78.989784 c 15.03631,-13.806637 25.47602,-22.073835 36.74025,-29.094513 8.88881,-5.540156 21.59109,-10.444558 27.05113,-10.444558 3.36626,0 15.21723,12.298726 24.78421,25.720611 14.81725,20.787711 25.71782,45.986976 31.24045,72.219686 3.56833,16.9498 3.8657,53.23126 0.57486,70.13935 -2.70068,13.87582 -8.40314,31.87484 -13.9661,44.08195 -4.16823,9.14657 -14.53521,26.91044 -19.0783,32.69074 -2.33569,2.97175 -2.33761,2.96527 -1.02393,-3.4477 z M 172.25917,33.104812 c -15.60147,-7.922671 -39.6696,-16.427164 -52.96493,-18.715209 -4.66097,-0.802124 -12.61193,-1.249474 -17.6688,-0.994114 -10.969613,0.55394 -10.479662,-0.0197 7.11783,-8.3336652 14.63023,-6.912081 26.83386,-10.976696 43.40044,-14.455218 18.6362,-3.9130858 53.66559,-3.9590088 72.00507,-0.0944 19.80818,4.174105 43.13297,12.854085 56.27623,20.9423862 l 3.90633,2.403927 -8.96247,-0.452584 c -17.81002,-0.899366 -43.76575,6.295879 -71.63269,19.857459 -8.40538,4.090523 -15.71788,7.357511 -16.25,7.25997 -0.53211,-0.09754 -7.38426,-3.43589 -15.22701,-7.418555 z" />
          </g>
        </svg>
      )}
    </span>
  );
}

export function PlatformDot({ platform }: { platform: string; locale?: Locale }) {
  return (
    <span className="plat-dot is-logo" title={platformLabel(platform, "ru")}>
      <PlatformLogo platform={platform} size={15} />
    </span>
  );
}

export function ScoreCup({
  locale,
  lines,
  onEmpty,
}: {
  locale: Locale;
  onEmpty?: () => void;
  lines: Array<{
    platform: string;
    count: number;
    day: number;
    month: number;
    extra?: string | null;
    unit?: string | null;
    tiers?: string | null;
  }>;
}) {
  const [open, setOpen] = useState(false);
  if (lines.length === 0) {
    if (!onEmpty) return null;
    return (
      <div className="score-cup">
        <button type="button" className="score-connect" onClick={onEmpty}>
          {t(locale, "join")}
        </button>
      </div>
    );
  }
  return (
    <div className="score-cup">
      <button
        type="button"
        className="score-cup-btn"
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        aria-expanded={open}
        aria-label={t(locale, "scoreSummary")}
      >
        <span className="score-plats">
          {lines.map((line) => (
            <PlatformLogo key={line.platform} platform={line.platform} size={18} />
          ))}
        </span>
      </button>
      {open ? (
        <Sheet onClose={() => setOpen(false)} closeLabel={t(locale, "close")} noClose>
          <div className="sheet-content score-sheet">
            <h2>{t(locale, "scoreSummary")}</h2>
            {lines.map((line) => (
              <div key={line.platform} className="score-row">
                <PlatformLogo platform={line.platform} size={22} />
                <strong>
                  {line.count.toLocaleString("ru-RU")}
                  {line.unit ? <small>{line.unit}</small> : null}
                </strong>
                {line.tiers ? <em>{line.tiers}</em> : null}
                <span className="score-meta">
                  {line.month.toLocaleString("ru-RU")} {t(locale, "homeMonthShort")}
                  <i aria-hidden> · </i>
                  {line.day.toLocaleString("ru-RU")} {t(locale, "homeDayShort")}
                </span>
              </div>
            ))}
          </div>
        </Sheet>
      ) : null}
    </div>
  );
}

export function Toggle({
  on,
  onClick,
  label,
}: {
  on: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      className={on ? "toggle is-on" : "toggle"}
      onClick={onClick}
    />
  );
}

export function meScoreLines(
  me: MeResponse,
  locale: Locale,
): Array<{
  platform: string;
  count: number;
  day: number;
  month: number;
    extra?: string | null;
    unit?: string | null;
    tiers?: string | null;
  }> {
  const lines: Array<{
    platform: string;
    count: number;
    day: number;
    month: number;
    extra?: string | null;
    unit?: string | null;
    tiers?: string | null;
  }> = [];
  if (me.xbox.linked) {
    lines.push({
      platform: "xbox",
      count: me.xbox.gamerscore ?? me.xbox.achievement_count,
      day: me.xbox.day,
      month: me.xbox.month,
      extra: me.xbox.completed_games ? `🌀 ${me.xbox.completed_games}` : null,
      unit: me.xbox.gamerscore != null ? "G" : null,
    });
  }
  if (me.psn.linked) {
    lines.push({
      platform: "psn",
      count: me.psn.trophy_count,
      day: me.psn.day,
      month: me.psn.month,
      extra: me.psn.trophy_level != null ? `${t(locale, "level")} ${me.psn.trophy_level}` : null,
      tiers: `🥉 ${me.psn.bronze} · 🥈 ${me.psn.silver} · 🥇 ${me.psn.gold} · 🏆 ${me.psn.platinum_count}`,
    });
  }
  if (me.steam.linked) {
    lines.push({
      platform: "steam",
      count: me.steam.achievement_count,
      day: me.steam.day,
      month: me.steam.month,
      extra: me.steam.completed_games ? `👾 ${me.steam.completed_games}` : null,
    });
  }
  return lines;
}

export function AccountBar({
  me,
  locale,
  onProfile,
  score = true,
}: {
  me: MeResponse;
  locale: Locale;
  onProfile: () => void;
  score?: boolean;
}) {
  const name = accountLabel(me);
  return (
    <header className="account-bar">
      <div className="account-top">
        <button type="button" className="account-who" onClick={onProfile}>
          <Avatar name={name} photo={telegramPhoto()} tgId={me.tg_id} size={48} />
          <span>
            <em className="hello">{t(locale, "hello")}</em>
            <strong>{name}</strong>
          </span>
        </button>
        {score ? <ScoreCup locale={locale} lines={meScoreLines(me, locale)} /> : null}
      </div>
    </header>
  );
}

export function SearchBar({
  locale,
  value,
  onChange,
}: {
  locale: Locale;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="search-bar">
      <Icon name="search" size={18} />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={t(locale, "searchHint")}
        enterKeyHint="search"
        autoComplete="off"
      />
      {value ? (
        <button
          type="button"
          className="search-clear"
          onClick={() => onChange("")}
          aria-label={t(locale, "close")}
        >
          ✕
        </button>
      ) : null}
    </label>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" />
      {label ? <p className="muted">{label}</p> : null}
    </div>
  );
}

/** Mobile-style pull-to-refresh at the top of the page scroll. */
export function usePullToRefresh(onRefresh: () => void | Promise<void>) {
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const startY = useRef(0);
  const pulling = useRef(false);
  const armed = useRef(false);
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;

  useEffect(() => {
    const THRESHOLD = 68;
    const MAX = 112;
    const onStart = (event: TouchEvent) => {
      if (document.documentElement.classList.contains("is-sheet-open")) return;
      if (refreshing) return;
      if (window.scrollY > 1) return;
      startY.current = event.touches[0]?.clientY ?? 0;
      pulling.current = true;
      armed.current = false;
    };
    const onMove = (event: TouchEvent) => {
      if (!pulling.current || refreshing) return;
      if (document.documentElement.classList.contains("is-sheet-open")) {
        pulling.current = false;
        setPull(0);
        return;
      }
      if (window.scrollY > 1) {
        pulling.current = false;
        setPull(0);
        return;
      }
      const y = event.touches[0]?.clientY ?? 0;
      const dy = y - startY.current;
      if (dy <= 0) {
        setPull(0);
        armed.current = false;
        return;
      }
      const next = Math.min(MAX, dy * 0.42);
      setPull(next);
      armed.current = next >= THRESHOLD;
      if (dy > 12) event.preventDefault();
    };
    const onEnd = () => {
      if (!pulling.current) return;
      pulling.current = false;
      if (armed.current) {
        setRefreshing(true);
        setPull(THRESHOLD);
        void Promise.resolve(refresh.current())
          .catch(() => undefined)
          .finally(() => {
            setRefreshing(false);
            setPull(0);
          });
      } else {
        setPull(0);
      }
      armed.current = false;
    };
    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: false });
    document.addEventListener("touchend", onEnd);
    document.addEventListener("touchcancel", onEnd);
    return () => {
      document.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
      document.removeEventListener("touchcancel", onEnd);
    };
  }, [refreshing]);

  const indicator =
    pull > 0 || refreshing
      ? createPortal(
          <div
            className={[
              "pull-refresh",
              refreshing ? "is-busy" : "",
              pull >= 68 && !refreshing ? "is-armed" : "",
            ]
              .filter(Boolean)
              .join(" ")}
            style={
              {
                height: Math.max(pull, refreshing ? 52 : 0),
                ["--pull-turn"]: String(Math.min(1, pull / 68)),
              } as CSSProperties
            }
            aria-hidden
          >
            <span className="pull-refresh-spinner" />
          </div>,
          document.body,
        )
      : null;

  return { indicator, refreshing };
}

export function Sheet({
  children,
  onClose,
  closeLabel,
  photo,
  tall,
  mid,
  compact,
  noClose: _noClose,
}: {
  children: ReactNode;
  onClose: () => void;
  closeLabel: string;
  photo?: boolean;
  tall?: boolean;
  /** Bottom sheet that stops a bit above mid-screen (month picker). */
  mid?: boolean;
  compact?: boolean;
  /** Kept for callers; close now lives above the drawer on the blur veil. */
  noClose?: boolean;
}) {
  const [leaving, setLeaving] = useState(false);
  const closed = useRef(false);
  // Ignore backdrop taps for a beat after open — the same finger-up that
  // opened the sheet otherwise lands on the fresh overlay and closes it.
  const armed = useRef(false);
  const finish = () => {
    if (closed.current) return;
    closed.current = true;
    onClose();
  };
  const close = () => setLeaving(true);
  useEffect(() => {
    armed.current = false;
    const id = window.setTimeout(() => {
      armed.current = true;
    }, 400);
    return () => window.clearTimeout(id);
  }, []);
  useEffect(() => {
    // Do not set overflow:hidden / position:fixed on body — Telegram's Mini
    // App chrome collapses when the page is taken out of the document flow.
    // Freeze the scroll offset instead, and keep the WebApp expanded.
    const html = document.documentElement;
    const y = window.scrollY;
    html.classList.add("is-sheet-open");
    window.Telegram?.WebApp?.expand?.();
    const freeze = () => {
      if (window.scrollY !== y) window.scrollTo(0, y);
    };
    const block = (event: TouchEvent) => {
      const node = event.target;
      if (!(node instanceof Element)) return;
      if (node.closest(".sheet-body")) return;
      event.preventDefault();
    };
    window.addEventListener("scroll", freeze, { passive: true });
    document.addEventListener("touchmove", block, { passive: false });
    return () => {
      html.classList.remove("is-sheet-open");
      window.removeEventListener("scroll", freeze);
      document.removeEventListener("touchmove", block);
      window.scrollTo(0, y);
    };
  }, []);
  useEffect(() => {
    if (!leaving) return;
    const id = window.setTimeout(finish, 340);
    return () => window.clearTimeout(id);
  }, [leaving]);
  return createPortal(
    <div
      className={["sheet", compact ? "is-compact" : "", leaving ? "is-leave" : ""]
        .filter(Boolean)
        .join(" ")}
      onClick={() => {
        if (!armed.current) return;
        close();
      }}
      onAnimationEnd={(e) => {
        if (leaving && e.target === e.currentTarget) finish();
      }}
      role="presentation"
    >
      <div className="sheet-stack">
        <button
          type="button"
          className="sheet-dismiss"
          onClick={(e) => {
            e.stopPropagation();
            close();
          }}
          aria-label={closeLabel}
        >
          ✕
        </button>
        <div
          className={[
            "sheet-body glass",
            photo ? "is-photo" : "",
            tall ? "is-tall" : "",
            mid ? "is-mid" : "",
            compact ? "is-compact" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={(e) => e.stopPropagation()}
          role="dialog"
        >
          {children}
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function SheetHero({
  src,
  secret,
  title,
  text,
  corner,
  lead,
  veil,
  children,
}: {
  src?: string | null;
  secret?: boolean;
  title: string;
  text?: string | null;
  corner?: ReactNode;
  lead?: ReactNode;
  veil?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className={secret ? "sheet-hero is-secret" : "sheet-hero"}>
      <div className="profile-hero-layers">
        <CoverImg src={src} kind="achievement" className="profile-hero-art" />
      </div>
      <div className="profile-hero-wash" />
      {lead}
      {corner}
      <div className="profile-hero-copy">
        <div className="profile-hero-words">
          <h2>{title}</h2>
          {text ? <p>{text}</p> : null}
          {children}
        </div>
      </div>
      {veil}
    </div>
  );
}

export function GlassWait({ tall = false }: { tall?: boolean }) {
  return (
    <div className={tall ? "glass-wait is-tall" : "glass-wait"} aria-hidden>
      <span className="glass-orb" />
      <span className="glass-orb" />
      <span className="glass-orb" />
    </div>
  );
}

export function BackHead({
  title,
  onBack,
  backLabel,
}: {
  title: string;
  onBack: () => void;
  backLabel: string;
}) {
  return (
    <header className="page-head">
      <button type="button" className="icon-btn" onClick={onBack} aria-label={backLabel}>
        <Icon name="back" size={26} />
      </button>
      <h1>{title}</h1>
    </header>
  );
}

export function PageSkel() {
  return (
    <div aria-busy="true" aria-live="polite">
      <span className="skel hero" />
      <span className="skel line" />
      <span className="skel line" style={{ width: "68%" }} />
      <div className="skel-row">
        <span className="skel circle" style={{ width: 58, height: 58 }} />
        <span>
          <span className="skel line" />
          <span className="skel line" style={{ width: "55%" }} />
        </span>
      </div>
      <div className="skel-row">
        <span className="skel circle" style={{ width: 58, height: 58 }} />
        <span>
          <span className="skel line" />
          <span className="skel line" style={{ width: "48%" }} />
        </span>
      </div>
    </div>
  );
}

export function HomeSkel() {
  return (
    <div className="profile-hero home-skel" aria-busy="true">
      <span className="skel home-skel-fill" />
    </div>
  );
}
