import { BaseApi } from "../base/baseApi";
import {
  API_BASE_ROUTES,
  GAMES_ROUTES,
} from "../../core/constants/routes";
import type {
  GameDetails,
  GameGuidesResponse,
} from "./gamesApiModels";

export class GamesApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.GAMES) {
    super(baseUrl);
  }

  fetchGame(
    initData: string,
    platform: string,
    titleId: string,
    opts?: { force?: boolean; personId?: number | null; tgId?: number | null },
  ): Promise<GameDetails> {
    return this.get<GameDetails>(
      initData,
      GAMES_ROUTES.TITLE(platform, titleId),
      opts?.force || opts?.personId || opts?.tgId
        ? {
            force: opts.force ? 1 : undefined,
            person: opts.personId ?? undefined,
            // A post's button from before person ids (#156).
            tg_id: opts.personId ? undefined : (opts.tgId ?? undefined),
          }
        : undefined,
    );
  }

  /** The Steam guides' tip for each achievement — asked once when the page opens. */
  fetchGameGuides(
    initData: string,
    platform: string,
    titleId: string,
  ): Promise<GameGuidesResponse> {
    return this.get<GameGuidesResponse>(
      initData,
      GAMES_ROUTES.GUIDES(platform, titleId),
    );
  }
}

export const gamesApi = new GamesApi();
