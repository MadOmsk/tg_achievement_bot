import type { Locale } from "../../../i18n";

/** The post as paragraphs, list lines kept together: Steam posts put a blank
 * line between nearly every line, which is far too airy to read. */
export function paragraphsOf(text: string): string[] {
  const out: string[] = [];
  for (const paragraph of text.split(/\n{2,}/)) {
    const isItem = paragraph.startsWith("- ");
    if (isItem && out.length > 0 && out[out.length - 1].startsWith("- ")) {
      out[out.length - 1] += `\n${paragraph}`;
    } else {
      out.push(paragraph);
    }
  }
  return out;
}

/** A post's hour and minute, in the reader's own time. */
export function clockOf(iso: string, locale: Locale): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime()) || iso.length <= 10) return "";
  return date.toLocaleTimeString(locale === "en" ? "en-GB" : "ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
