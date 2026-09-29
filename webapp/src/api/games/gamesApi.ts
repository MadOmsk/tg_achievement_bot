import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES, GAMES_ROUTES } from "../../components/shared/constants/routes";
import type { GameDetails, GameHltbResponse } from "./gamesApiModels";

export class GamesApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.GAMES) {
    super(baseUrl);
  }

  fetchGame(
    initData: string,
    platform: string,
    titleId: string,
    opts?: { force?: boolean; tgId?: number | null },
  ): Promise<GameDetails> {
    return this.get<GameDetails>(
      initData,
      GAMES_ROUTES.TITLE(platform, titleId),
      opts?.force || opts?.tgId
        ? { force: opts.force ? 1 : undefined, tg_id: opts.tgId ?? undefined }
        : undefined,
    );
  }

  /** HowLongToBeat's own card for this game (#131) — its own request, so a
   * game's first-ever match (a few HLTB requests) never delays the
   * achievements `fetchGame` above already answers with. */
  fetchGameHltb(initData: string, platform: string, titleId: string): Promise<GameHltbResponse> {
    return this.get<GameHltbResponse>(initData, GAMES_ROUTES.HLTB(platform, titleId));
  }
}

export const gamesApi = new GamesApi();
