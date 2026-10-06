import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES } from "../../components/shared/constants/routes";

/** One of the app's own notifications (#164), already worded by the server. */
export type NotificationItem = {
  id: number;
  kind: string;
  text: string;
  /** The list's line: after the name in bold (or the whole line, with no name). */
  lead: string;
  /** What it is about — an achievement and its game. */
  detail: string | null;
  /** Its picture, at the row's end. */
  image: string | null;
  created_at: string;
  read: boolean;
  /** Whom a tap opens, when the notice is about somebody. */
  person_id: number | null;
  /** That person's nickname, for their face's initials. */
  name: string | null;
  /** The game a tap opens, on that person's progress (a new post). */
  game: { platform: string; title_id: string; name: string | null } | null;
};

export class NotificationsApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.MINI) {
    super(baseUrl);
  }

  list(initData: string): Promise<{ items: NotificationItem[]; unread: number }> {
    return this.get(initData, "/notifications");
  }

  /** Mark these notices read; with no ids, all of them. */
  markRead(initData: string, ids?: number[]): Promise<{ ok: boolean; unread: number }> {
    return this.post(initData, "/notifications/read", ids ? { ids } : {});
  }

  pushKey(initData: string): Promise<{ available: boolean; public_key: string | null }> {
    return this.get(initData, "/push/key");
  }

  subscribe(initData: string, subscription: PushSubscriptionJSON): Promise<{ ok: boolean }> {
    return this.post(initData, "/push/subscription", subscription);
  }

  unsubscribe(initData: string, endpoint: string): Promise<{ ok: boolean }> {
    return this.request(initData, "/push/subscription", {
      method: "DELETE",
      body: JSON.stringify({ endpoint }),
    });
  }
}

export const notificationsApi = new NotificationsApi();
