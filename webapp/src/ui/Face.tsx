import { useState } from "react";
import { USER_ROUTES, API_BASE_ROUTES } from "../core/constants";

export type Presence = "playing" | "online" | null;

export function faceUrl(personId: number): string {
  return `${API_BASE_ROUTES.MINI}${USER_ROUTES.AVATAR(personId)}`;
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
  const [failed, setFailed] = useState(false);
  if (name && name !== "?") seenNames.set(personId, name);
  const ring = presence ? Math.max(thinRing ? 2 : 3, Math.round(size * (thinRing ? 0.05 : 0.08))) : 0;
  const inner = size - ring * 2;
  const src = `${faceUrl(personId)}${version ? `?v=${version}` : ""}`;
  return (
    <span
      className={`face${dim ? " face-dim" : ""}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={name}
    >
      {presence && <span className={`face-ring shape-cookie12 face-ring-${presence}`} />}
      <span className="face-in shape-cookie12" style={{ inset: ring, width: inner, height: inner }}>
        {failed ? (
          <span className="face-initials" style={{ fontSize: Math.round(inner * 0.36) }}>
            {initials(name)}
          </span>
        ) : (
          <img src={src} alt="" loading="lazy" onError={() => setFailed(true)} />
        )}
      </span>
    </span>
  );
}
