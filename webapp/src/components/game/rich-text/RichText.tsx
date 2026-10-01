import type { ReactNode } from "react";
import { Icon } from "../../shared/lib";

// `[label](https://…)` from the backend, or a bare address in the text. A guide
// names the site right after its link, `[mapgenie.io]`; that is swallowed, the
// link's own words are the name.
const LINK =
  /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)(?:\[((?:[a-z0-9-]+\.)+[a-z]{2,})\])?|(https?:\/\/[^\s)]+)/gi;
// A table row arrives as one line, its cells joined by this mark.
const CELL = " \u00a6 ";

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

/** The words only, for text that is not tappable; videos left out, a table's
 * cells run together. */
export function withoutLinks(text: string): string {
  return text
    .split(CELL)
    .join(" \u00b7 ")
    .split("\n")
    .filter((line) => videoOf(line) === null && imageOf(line) === null)
    .join("\n")
    .replace(
      LINK,
      (
        _all,
        label: string | undefined,
        _url,
        _site,
        bare: string | undefined,
      ) =>
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
    const url = match[2] ?? match[4];
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

function Table({ rows }: { rows: string[] }) {
  const cells = rows.map((row) => row.split(CELL));
  const [head, ...body] = cells;
  // A first row over at least two more is the table's heading.
  const headed = body.length >= 2;
  return (
    <span className="rich-table-wrap">
      <table className="rich-table">
        {headed && (
          <thead>
            <tr>
              {head.map((cell, i) => (
                <th key={i}>{linked(cell)}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {(headed ? body : cells).map((row, r) => (
            <tr key={r}>
              {row.map((cell, i) => (
                <td key={i}>{linked(cell)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </span>
  );
}

/** Text as lines: links tappable, a YouTube address alone on its line a video
 * card, a picture's address a picture, consecutive table rows a table.
 * `className` goes on each line. */
export function RichLines({
  text,
  className,
}: {
  text: string;
  className: string;
}) {
  const out: ReactNode[] = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.includes(CELL)) {
      const start = i;
      while (i + 1 < lines.length && lines[i + 1].includes(CELL)) i += 1;
      out.push(<Table key={start} rows={lines.slice(start, i + 1)} />);
      continue;
    }
    const video = videoOf(line);
    if (video) {
      out.push(<VideoCard key={i} id={video} />);
      continue;
    }
    const image = imageOf(line);
    if (image) {
      out.push(
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
        />,
      );
      continue;
    }
    out.push(
      <span key={i} className={className}>
        {linked(line)}
      </span>,
    );
  }
  return <>{out}</>;
}
