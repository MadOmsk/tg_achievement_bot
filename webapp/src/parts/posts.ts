import type { FeedItem } from "../api";
import { dayKey } from "../i18n";

/** One unlock as people saw it: one achievement, earned by one person — or by
 * several who played together and got it within minutes of each other. */
export type UnlockEvent = { at: number; items: FeedItem[] };

/** A post: one day, one game, the same people, their unlocks newest first. */
export type Post = {
  key: string;
  day: string;
  platform: string;
  titleId: string;
  game: string | null;
  gameIcon: string | null;
  gameId: number | null;
  people: Array<{ id: number; name: string }>;
  events: UnlockEvent[];
};

const TOGETHER_MS = 10 * 60 * 1000;

function timeOf(item: FeedItem): number {
  const t = item.unlocked_at ? Date.parse(item.unlocked_at) : NaN;
  return Number.isNaN(t) ? 0 : t;
}

/** The feed, newest first, as posts: the same achievement got by several
 * people within ten minutes is one unlock "together", and the unlocks of one
 * game by the same people on one day run on as one post. */
export function toPosts(items: FeedItem[]): Post[] {
  const events: UnlockEvent[] = [];
  const open = new Map<string, UnlockEvent>();
  for (const item of items) {
    const key = `${item.platform}:${item.title_id}:${item.achievement_id}:${dayKey(item.unlocked_at)}`;
    const at = timeOf(item);
    const event = open.get(key);
    if (
      event &&
      Math.abs(event.at - at) <= TOGETHER_MS &&
      !event.items.some((x) => x.person_id === item.person_id)
    ) {
      event.items.push(item);
      continue;
    }
    const fresh = { at, items: [item] };
    open.set(key, fresh);
    events.push(fresh);
  }
  const posts: Post[] = [];
  for (const event of events) {
    const first = event.items[0];
    const day = dayKey(first.unlocked_at);
    const who = event.items.map((x) => x.person_id).sort((a, b) => a - b).join(",");
    const last = posts[posts.length - 1];
    if (
      last &&
      last.day === day &&
      last.platform === first.platform &&
      last.titleId === first.title_id &&
      last.people.map((p) => p.id).sort((a, b) => a - b).join(",") === who
    ) {
      last.events.push(event);
      continue;
    }
    posts.push({
      key: `${first.platform}:${first.title_id}:${first.achievement_id}:${who}:${event.at}`,
      day,
      platform: first.platform,
      titleId: first.title_id,
      game: first.game,
      gameIcon: first.game_poster ?? first.game_icon_url,
      gameId: first.game_id ?? null,
      people: event.items.map((x) => ({ id: x.person_id, name: x.person })),
      events: [event],
    });
  }
  return posts;
}

/** Each person's progress in the post's game, as of their latest unlock in it. */
export function progressOf(post: Post): Array<{ id: number; unlocked: number; total: number | null }> {
  return post.people.map((p) => {
    for (const event of post.events) {
      const item = event.items.find((x) => x.person_id === p.id);
      if (item?.progress) return { id: p.id, unlocked: item.progress.unlocked, total: item.progress.total };
    }
    return { id: p.id, unlocked: 0, total: null };
  });
}
