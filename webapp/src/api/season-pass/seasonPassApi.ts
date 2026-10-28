import { BaseApi, WEB_SESSION } from "../base/baseApi";
import type { GameCard } from "../game/gameApiModels";
import { API_BASE_ROUTES } from "../../core/constants/routes";

export type Look = "common" | "rare" | "legendary" | "mythic";

export type PassTier = {
  id: number;
  level: number;
  points: number;
  tier: Look;
  palette: string;
  claimed: boolean;
};

/** A prize of the super-admin's: a stack of codes, one to a person. `code`
 * is the viewer's own, once taken. */
export type PassReward = {
  id: number;
  title: string;
  description: string | null;
  points: number;
  /** A game of ours (its card from the catalog), or a code for something else. */
  kind: "game" | "code";
  game: GameCard | null;
  /** The platform it is for, when said. */
  platform: string | null;
  /** The super-admin's picture of it, if one was sent. */
  image: string | null;
  total: number;
  left: number;
  code: string | null;
  removed: boolean;
};

/** A level as the super-admin edits it: its draft laid over it. */
export type PassEditorItem = {
  id: number;
  kind: "theme" | "game" | "code";
  palette: string | null;
  tier: Look | null;
  title: string | null;
  description: string | null;
  points: number;
  game: GameCard | null;
  platform: string | null;
  image: string | null;
  codes: string[];
  /** New, not published yet. */
  draft: boolean;
  /** Published, with changes waiting for the publish. */
  changed: boolean;
  /** Published, to be taken down at the publish. */
  remove: boolean;
  /** How many have it: anything above 0 locks it. */
  taken: number;
};

export type PassEditor = {
  /** The month whose pass is edited, and the months that may be: this one
   * and the ones ahead, each with its levels and the ones waiting to publish. */
  month: string;
  months: { month: string; levels: number; dirty: number }[];
  /** The month's pass's name as the draft has it, and whether it waits to publish. */
  title: string | null;
  title_changed: boolean;
  /** What people score in a month: this month's best so far, last month's
   * best and middle among those who scored. */
  scores: { top: number; last_top: number; last_median: number };
  /** Levels the next publish changes. */
  dirty: number;
  palettes: string[];
  items: PassEditorItem[];
};

export type PassState = {
  ok: boolean;
  month: string;
  points: number;
  days_left: number;
  tiers: PassTier[];
  rewards: PassReward[];
  /** The viewer edits the pass. */
  admin: boolean;
  editor?: PassEditor;
  /** This month's pass; false: an earlier one, only to look back on. */
  current: boolean;
  /** The months with a pass, the latest first. */
  months: string[];
  /** The month's theme, its pass's name: "Хэллоуин". */
  title: string | null;
};

/** A level as the editor sends it. */
export type PassItemInput = {
  kind: "theme" | "game" | "code";
  points: number;
  palette?: string;
  tier?: Look;
  title?: string;
  description?: string;
  game_id?: number | null;
  platform?: string | null;
  codes?: string[];
};

export type PassTaker = { person_id: number; name: string; claimed_at: string };

export type Published = { added: number; changed: number; removed: number; skipped: number };

function query(params: Record<string, string | null | undefined>): string {
  const set = Object.entries(params).filter((e): e is [string, string] => Boolean(e[1]));
  return set.length ? `?${new URLSearchParams(set).toString()}` : "";
}

/** The season pass: the server says what is reached and judges every claim. */
export class PassApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.MINI) {
    super(baseUrl);
  }

  /** `month`: an earlier month's pass; `edit`: the month the editor shows. */
  fetchPass(initData: string, opts: { month?: string | null; edit?: string | null } = {}): Promise<PassState> {
    return this.get<PassState>(initData, `/pass${query({ month: opts.month, edit: opts.edit })}`);
  }

  claim(initData: string, palette: string): Promise<PassState> {
    return this.post<PassState>(initData, "/pass/claim", { palette });
  }

  claimReward(initData: string, id: number): Promise<PassState> {
    return this.post<PassState>(initData, `/pass/items/${id}/claim`);
  }

  takers(initData: string, id: number): Promise<{ ok: boolean; takers: PassTaker[] }> {
    return this.get<{ ok: boolean; takers: PassTaker[] }>(initData, `/pass/items/${id}/takers`);
  }

  // The editor's calls name the month they edit (`edit`).
  addItem(initData: string, edit: string | null, item: PassItemInput): Promise<PassState & { added: number }> {
    return this.post<PassState & { added: number }>(initData, `/pass/items${query({ edit })}`, item);
  }

  editItem(initData: string, edit: string | null, id: number, item: PassItemInput): Promise<PassState> {
    return this.patch<PassState>(initData, `/pass/items/${id}${query({ edit })}`, item);
  }

  removeItem(initData: string, edit: string | null, id: number): Promise<PassState> {
    return this.delete<PassState>(initData, `/pass/items/${id}${query({ edit })}`);
  }

  revertItem(initData: string, edit: string | null, id: number): Promise<PassState> {
    return this.post<PassState>(initData, `/pass/items/${id}/revert${query({ edit })}`);
  }

  /** A level's picture: the bytes as they are, saved again by the server. */
  async putItemImage(initData: string, edit: string | null, id: number, image: Blob): Promise<PassState> {
    const headers: Record<string, string> = { "Content-Type": image.type || "image/jpeg" };
    if (initData !== WEB_SESSION) headers["X-Telegram-Init-Data"] = initData;
    const response = await fetch(this.buildUrl(`/pass/items/${id}/image${query({ edit })}`), { method: "PUT", headers, body: image });
    if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
    return (await response.json()) as PassState;
  }

  seasonTitle(initData: string, edit: string | null, title: string): Promise<PassState> {
    return this.put<PassState>(initData, `/pass/season${query({ edit })}`, { title });
  }

  publish(initData: string, edit: string | null, notify: boolean): Promise<PassState & { published: Published }> {
    return this.post<PassState & { published: Published }>(initData, `/pass/publish${query({ edit })}`, { notify });
  }

  discard(initData: string, edit: string | null): Promise<PassState> {
    return this.post<PassState>(initData, `/pass/discard${query({ edit })}`);
  }
}

export const passApi = new PassApi();
