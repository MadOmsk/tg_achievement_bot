import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES, HLTB_ROUTES } from "../../components/shared/constants/routes";
import type { HltbHit } from "./hltbApiModels";

export class HltbApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.HLTB) {
    super(baseUrl);
  }

  search(initData: string, query: string): Promise<{ results: HltbHit[] }> {
    return this.get<{ results: HltbHit[] }>(initData, HLTB_ROUTES.SEARCH, { q: query });
  }

  resolve(initData: string, id: number): Promise<HltbHit> {
    return this.get<HltbHit>(initData, HLTB_ROUTES.RESOLVE(id));
  }
}

export const hltbApi = new HltbApi();
