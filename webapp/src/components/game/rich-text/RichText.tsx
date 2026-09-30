import type { ReactNode } from "react";
import { Icon } from "../../shared/lib";

// `[label](https://…)` from the backend, or a bare address in the text.
const LINK = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s)]+)/g;
// A YouTube address alone on its line is a video, drawn as a card.
const YOUTUBE =
  /^(?:\[[^\]]*\]\()?https?:\/\/(?:www\.|m\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)([A-Za-z0-9_-]{11})[^\s)]*\)?$/;

// A picture's address alone on its line (a guide's screenshot) is shown.
const IMAGE =
  /^(?:\[[^\]]*\]\()?(https?:\/\/(?:images\.steamusercontent\.com\/ugc\/[^\s)]+|[^\s)]+\.(?:jpe?g|png|gif|webp)))\)?$/i;

export function openUrl(url: string) {
  if (window.Telegram?.WebApp?.openLink) window.Telegram.WebApp.openLink(url);
  else window.open(url, "_blank", "noopener");
}

function videoOf(line: string): string | null {
  return YOUTUBE.exec(line.trim())?.[1] ?? null;
}

function imageOf(line: string): string | null {
  return IMAGE.exec(line.trim())?.[1] ?? null;
}

/** The words only, for text that is not tappable; videos left out. */
export function withoutLinks(text: string): string {
  return text
    .split("\n")
    .filter((line) => videoOf(line) === null && imageOf(line) === null)
    .join("\n")
    .replace(
      LINK,
      (_all, label: string | undefined, _url, bare: string | undefined) =>
        label ?? bare ?? "",
    );
}

/** One line with its addresses made into links. */
function linked(line: string): ReactNode[] {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of line.matchAll(LINK)) {
    const index = match.index ?? 0;
    if (index > last) parts.push(line.slice(last, index));
    const url = match[2] ?? match[3];
    parts.push(
      <a
        key={index}
        href={url}
        className="rich-link"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          openUrl(url);
        }}
      >
        {match[1] ?? url}
      </a>,
    );
    last = index + match[0].length;
  }
  if (last < line.length) parts.push(line.slice(last));
  return parts;
}

function VideoCard({ id }: { id: string }) {
  return (
    <span
      role="link"
      tabIndex={0}
      className="rich-video"
      onClick={(event) => {
        event.stopPropagation();
        openUrl(`https://www.youtube.com/watch?v=${id}`);
      }}
    >
      <img
        src={`https://i.ytimg.com/vi/${id}/mqdefault.jpg`}
        alt=""
        loading="lazy"
      />
      <span className="rich-video-play" aria-hidden>
        <Icon name="forward" size={20} />
      </span>
    </span>
  );
}

/** Text as lines: links tappable, a YouTube address alone on its line a video
 * card, a picture's address a picture. `className` goes on each line. */
export function RichLines({
  text,
  className,
}: {
  text: string;
  className: string;
}) {
  return (
    <>
      {text.split("\n").map((line, i) => {
        const video = videoOf(line);
        if (video) return <VideoCard key={i} id={video} />;
        const image = imageOf(line);
        if (image) {
          return (
            <img
              key={i}
              className="rich-image"
              src={image}
              alt=""
              loading="lazy"
              onClick={(event) => {
                event.stopPropagation();
                openUrl(image);
              }}
            />
          );
        }
        return (
          <span key={i} className={className}>
            {linked(line)}
          </span>
        );
      })}
    </>
  );
}
