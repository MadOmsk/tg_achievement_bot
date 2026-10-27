import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES } from "../../core/constants/routes";

export type PassTier = {
  level: number;
  points: number;
  tier: "common" | "rare" | "legendary" | "mythic";
  palette: string;
  claimed: boolean;
};

export type PassState = {
  ok: boolean;
  month: string;
  points: number;
  days_left: number;
  tiers: PassTier[];
};

/** The season pass: the server says what is reached and judges every claim. */
export class PassApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.MINI) {
    super(baseUrl);
  }

  fetchPass(initData: string): Promise<PassState> {
    return this.get<PassState>(initData, "/pass");
  }

  claim(initData: string, palette: string): Promise<PassState> {
    return this.post<PassState>(initData, "/pass/claim", { palette });
  }
}

export const passApi = new PassApi();
