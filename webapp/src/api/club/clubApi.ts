import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES, CLUB_ROUTES } from "../../components/shared/constants/routes";
import type { FeedResponse, NewsResponse, OnlineMember, PersonPayload, SummaryResponse } from "./clubApiModels";

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

  /** Game news: what the developers of the games one's circle plays posted. */
  fetchNews(initData: string, opts?: { month?: string }): Promise<NewsResponse> {
    return this.get<NewsResponse>(initData, CLUB_ROUTES.NEWS, { scope: "following", month: opts?.month });
  }

  fetchOnline(
    initData: string,
    chatId: number | "following",
  ): Promise<{ members: OnlineMember[] }> {
    return this.get<{ members: OnlineMember[] }>(initData, CLUB_ROUTES.ONLINE, scopeQuery(chatId));
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

  /** A person's page; `chatId` is the chat it was opened from, if any. */
  fetchPerson(
    initData: string,
    chatId: number | null,
    personId: number,
    opts?: { month?: string },
  ): Promise<PersonPayload> {
    return this.get<PersonPayload>(initData, CLUB_ROUTES.PEOPLE, {
      chat_id: chatId ?? undefined,
      person: personId,
      month: opts?.month,
    });
  }
}

export const clubApi = new ClubApi();
