import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "../icon/Icon";
import { useImgFade } from "../img-fade/useImgFade";
import "./CoverImg.css";

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
  const [failed, setFailed] = useState(false);
  const fade = useImgFade(url);

  useEffect(() => {
    setFailed(false);
  }, [url]);

  const hasImg = Boolean(url && !failed);
  const hero = Boolean(className?.includes("profile-hero-art"));
  const gameHero = Boolean(className?.includes("game-card-art"));
  const markSize = hero ? 96 : gameHero ? 112 : 28;
  return (
    <span
      className={["cover-ph", `is-${kind}`, hasImg ? "has-img" : "is-empty", className]
        .filter(Boolean)
        .join(" ")}
    >
      {hasImg ? (
        <img
          ref={fade.ref}
          src={url}
          alt=""
          className={[imgClassName, fade.className].filter(Boolean).join(" ")}
          draggable={false}
          loading="eager"
          onLoad={fade.onLoad}
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="cover-ph-mark" aria-hidden>
          <CoverMark kind={kind} size={markSize} />
        </span>
      )}
      {children}
    </span>
  );
}

/** The glyph an empty cover shows: a cup for an achievement, a pad for a game. */
export function CoverMark({
  kind,
  size,
}: {
  kind: "game" | "achievement";
  size: number;
}) {
  return kind === "achievement" ? (
    <Icon name="cup" size={size} filled />
  ) : (
    <GamePadMark size={size} />
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
