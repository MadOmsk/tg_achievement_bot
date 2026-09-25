import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES, CLUB_ROUTES } from "../../components/shared/constants/routes";
import type { FeedResponse, OnlineMember, PersonPayload, SummaryResponse } from "./clubApiModels";

export class ClubApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.CLUB) {
    super(baseUrl);
  }

  fetchFeed(
    initData: string,
    chatId: number,
    opts?: { limit?: number; month?: string },
  ): Promise<FeedResponse> {
    return this.get<FeedResponse>(initData, CLUB_ROUTES.FEED, {
      chat_id: chatId,
      limit: opts?.limit,
      month: opts?.month,
    });
  }

  fetchOnline(initData: string, chatId: number): Promise<{ members: OnlineMember[] }> {
    return this.get<{ members: OnlineMember[] }>(initData, CLUB_ROUTES.ONLINE, { chat_id: chatId });
  }

  fetchSummary(
    initData: string,
    chatId: number,
    opts?: { month?: string },
  ): Promise<SummaryResponse> {
    return this.get<SummaryResponse>(initData, CLUB_ROUTES.SUMMARY, {
      chat_id: chatId,
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
