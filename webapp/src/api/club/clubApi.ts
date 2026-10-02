import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES, CLUB_ROUTES } from "../../components/shared/constants/routes";
import type { FeedResponse, OnlineMember, PersonPayload, SummaryResponse } from "./clubApiModels";

/** One chat, or the people you follow (#157). */
function scopeQuery(scope: number | "following"): Record<string, string | number> {
  return scope === "following" ? { scope: "following" } : { chat_id: scope };
}

export class ClubApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.CLUB) {
    super(baseUrl);
  }

  fetchFeed(
    initData: string,
    chatId: number | "following",
    opts?: { limit?: number; month?: string },
  ): Promise<FeedResponse> {
    return this.get<FeedResponse>(initData, CLUB_ROUTES.FEED, {
      ...scopeQuery(chatId),
      limit: opts?.limit,
      month: opts?.month,
    });
  }

  fetchOnline(initData: string, chatId: number): Promise<{ members: OnlineMember[] }> {
    return this.get<{ members: OnlineMember[] }>(initData, CLUB_ROUTES.ONLINE, { chat_id: chatId });
  }

  fetchSummary(
    initData: string,
    chatId: number | "following",
    opts?: { month?: string },
  ): Promise<SummaryResponse> {
    return this.get<SummaryResponse>(initData, CLUB_ROUTES.SUMMARY, {
      ...scopeQuery(chatId),
      month: opts?.month,
    });
  }

  fetchPerson(
    initData: string,
    chatId: number,
    tgId: number,
    opts?: { month?: string },
  ): Promise<PersonPayload> {
    return this.get<PersonPayload>(initData, CLUB_ROUTES.PEOPLE, {
      chat_id: chatId,
      tg_id: tgId,
      month: opts?.month,
    });
  }
}

export const clubApi = new ClubApi();
