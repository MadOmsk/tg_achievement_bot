import { useEffect, useState } from "react";
import { fetchAvatarBlob, WEB_SESSION } from "../api";
import { USER_ROUTES, API_BASE_ROUTES } from "../core/constants";
import { initData } from "../core/launch";

export type Presence = "playing" | "online" | null;

export function faceUrl(personId: number): string {
  return `${API_BASE_ROUTES.MINI}${USER_ROUTES.AVATAR(personId)}`;
}

/** Inside Telegram a face is fetched with Init Data (a bare <img> carries no
 * header and is refused) and kept as an object URL; null means no picture. */
const loaded = new Map<string, Promise<string | null>>();

/** Where a face's picture can be read from: its address in a browser, where the
 * session cookie signs it; inside Telegram an object URL fetched once. */
export function faceSrc(personId: number, version?: number): Promise<string | null> {
  const data = initData();
  if (!data || data === WEB_SESSION) {
    return Promise.resolve(`${faceUrl(personId)}${version ? `?v=${version}` : ""}`);
  }
  const key = `${personId}:${version ?? 0}`;
  let src = loaded.get(key);
  if (!src) {
    src = fetchAvatarBlob(data, personId).then(
      (blob) => (blob ? URL.createObjectURL(blob) : null),
      () => {
        loaded.delete(key); // a failed request is asked again by the next face
        return null;
      },
    );
    loaded.set(key, src);
  }
  return src;
}

/** The names faces were drawn with, so a page about a person can name them
 * while their card is on its way. */
const seenNames = new Map<number, string>();

export function knownName(personId: number): string | undefined {
  return seenNames.get(personId);
}

function initials(name: string): string {
  const clean = name.replace(/#\d+$/, "").trim();
  return (clean.slice(0, 2) || "?").toUpperCase();
}

/** A person's face, cut as a scalloped "cookie"; a ring of it says they are
 * playing (primary) or online (muted). Initials when there is no picture. */
export function Face({
  personId,
  name,
  size = 44,
  presence = null,
  dim = false,
  thinRing = false,
  version,
}: {
  personId: number;
  name: string;
  size?: number;
  presence?: Presence;
  dim?: boolean;
  thinRing?: boolean;
  /** Changes when one's own picture changes, so the new one shows at once. */
  version?: number;
}) {
  // undefined while loading, null when there is no picture
  const [src, setSrc] = useState<string | null | undefined>(undefined);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    setFailed(false);
    faceSrc(personId, version).then((s) => live && setSrc(s));
    return () => {
      live = false;
    };
  }, [personId, version]);
  if (name && name !== "?") seenNames.set(personId, name);
  const ring = presence ? Math.max(thinRing ? 2 : 3, Math.round(size * (thinRing ? 0.05 : 0.08))) : 0;
  const inner = size - ring * 2;
  return (
    <span
      className={`face${dim ? " face-dim" : ""}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={name}
    >
      {presence && <span className={`face-ring shape-cookie12 face-ring-${presence}`} />}
      <span className="face-in shape-cookie12" style={{ inset: ring, width: inner, height: inner }}>
        {failed || src === null ? (
          <span className="face-initials" style={{ fontSize: Math.round(inner * 0.36) }}>
            {initials(name)}
          </span>
        ) : src ? (
          <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />
        ) : null}
      </span>
    </span>
  );
}
