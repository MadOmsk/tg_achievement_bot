import type { ReactNode } from "react";
import { openExternal } from "../app/env";
import { paragraphsOf } from "../core/post-text";
import { Icon } from "./Icon";
import { openImage } from "./Viewer";

// A picture by its file's ending, or one of Steam's hosts that serve
// pictures under bare hashes (a guide's screenshots, a post's clan images).
const PICTURE =
  /^https?:\/\/(?:\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?|(?:images\.steamusercontent\.com|steamuserimages-a\.akamaihd\.net)\/ugc\/\S+|clan\.(?:akamai|fastly|cloudflare)\.steamstatic\.com\/images\/\S+)$/i;
const VIDEO = /^https?:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([\w-]{6,})\S*$/i;
// A link written as [label](url), or an address left bare in the text.
const LINK = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)|(https?:\/\/[^\s<>()]+[^\s<>().,;:!?'"])/g;

/** A line as it reads: trimmed, and a list's dash taken off — a guide often
 * lists its pictures as "- https://…". */
function bareLine(raw: string): string {
  return raw.trim().replace(/^[-*]\s+/, "");
}

/** A bare address shown short: its host and the start of its path. */
function shortUrl(url: string): string {
  const bare = url.replace(/^https?:\/\/(www\.)?/, "");
  return bare.length > 42 ? `${bare.slice(0, 40)}…` : bare;
}

/** A line's links as buttons that open outside through the right opener. */
function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(LINK)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const url = m[2] ?? m[3];
    out.push(
      <button key={`${m.index}`} type="button" className="rt-link" onClick={() => openExternal(url)}>
        {m[1] ?? shortUrl(url)}
      </button>,
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

/** A guide's tip or a developer's post: paragraphs, lists, links; a picture
 * or a video address on a line of its own becomes a picture or a video card. */
export function RichText({ text, className = "" }: { text: string; className?: string }) {
  const pictures = text
    .split("\n")
    .map(bareLine)
    .filter((l) => PICTURE.test(l));
  return (
    <div className={`rt ${className}`}>
      {paragraphsOf(text).map((para, i) => {
        const lines = para.split("\n");
        const pictureLines = lines.every((l) => PICTURE.test(bareLine(l)));
        if (!pictureLines && lines.every((l) => l.startsWith("- "))) {
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.slice(2))}</li>
              ))}
            </ul>
          );
        }
        return (
          <div key={i} className="rt-p">
            {lines.map((raw, j) => {
              const line = bareLine(raw);
              if (PICTURE.test(line)) {
                return (
                  <button key={j} type="button" className="rt-pic" onClick={() => openImage(line, pictures)}>
                    <img src={line} alt="" loading="lazy" />
                  </button>
                );
              }
              const video = VIDEO.exec(line);
              if (video) {
                return (
                  <button key={j} type="button" className="rt-video" onClick={() => openExternal(line)}>
                    <img src={`https://i.ytimg.com/vi/${video[1]}/mqdefault.jpg`} alt="" loading="lazy" />
                    <span className="rt-play shape-cookie9">
                      <Icon name="play" size={22} />
                    </span>
                  </button>
                );
              }
              return (
                <p key={j}>
                  {inline(raw)}
                </p>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
