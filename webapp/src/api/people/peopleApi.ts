import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES } from "../../components/shared/constants/routes";

/** What one person is to another, from the viewer's side (#157). */
export type Relation = {
  following: boolean;
  followed_by: boolean;
  friends: boolean;
  blocked: boolean;
};

export type PersonRow = {
  id: number;
  tg_id: number | null;
  /** The nickname as shown, with its digits. */
  handle: string;
  relation: Relation;
};

export type PersonProfile = PersonRow & {
  followers: number;
  following: number;
  /** May the viewer see this person's activity (their privacy setting)? */
  can_view: boolean;
  /** Their play, when their privacy lets the viewer see it. */
  activity: {
    presence: { state: string | null; playing: boolean; title_name?: string | null } | null;
    platforms: Array<{
      platform: string;
      name: string | null;
      achievement_count?: number;
      trophy_count?: number;
    }>;
    month: { count: number };
    recent: Array<{
      platform: string;
      title_id: string;
      achievement_id: string;
      name: string;
      game: string | null;
      icon_url: string | null;
      is_secret: boolean;
    }>;
  } | null;
};

export type ActivityVisible = "all" | "friends" | "nobody";

type People = { people: PersonRow[] };
type Rel = { relation: Relation };

export class PeopleApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.MINI) {
    super(baseUrl);
  }

  search(initData: string, q: string): Promise<People> {
    return this.get<People>(initData, "/people/search", { q });
  }

  suggestions(initData: string): Promise<People> {
    return this.get<People>(initData, "/people/suggestions");
  }

  following(initData: string): Promise<People> {
    return this.get<People>(initData, "/me/following");
  }

  followers(initData: string): Promise<People> {
    return this.get<People>(initData, "/me/followers");
  }

  blocked(initData: string): Promise<People> {
    return this.get<People>(initData, "/me/blocked");
  }

  profile(initData: string, id: number): Promise<PersonProfile> {
    return this.get<PersonProfile>(initData, `/people/${id}`);
  }

  follow(initData: string, id: number): Promise<Rel> {
    return this.post<Rel>(initData, `/people/${id}/follow`);
  }

  unfollow(initData: string, id: number): Promise<Rel> {
    return this.delete<Rel>(initData, `/people/${id}/follow`);
  }

  removeFollower(initData: string, id: number): Promise<Rel> {
    return this.delete<Rel>(initData, `/people/${id}/follower`);
  }

  block(initData: string, id: number): Promise<Rel> {
    return this.post<Rel>(initData, `/people/${id}/block`);
  }

  unblock(initData: string, id: number): Promise<Rel> {
    return this.delete<Rel>(initData, `/people/${id}/block`);
  }

  privacy(initData: string): Promise<{ activity_visible: ActivityVisible }> {
    return this.get(initData, "/me/privacy");
  }

  setPrivacy(initData: string, value: ActivityVisible): Promise<{ activity_visible: ActivityVisible }> {
    return this.put(initData, "/me/privacy", { activity_visible: value });
  }
}

export const peopleApi = new PeopleApi();
