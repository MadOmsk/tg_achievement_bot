import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES } from "../../components/shared/constants/routes";
import type { GameCard, GamePage } from "./gameApiModels";

/** The game page, the games search and favorite games (#147, stage 5). */
export class GameApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.MINI) {
    super(baseUrl);
  }

  /** A game whole: by its id, or by one of its achievement lists. */
  fetchGamePage(
    initData: string,
    ref: { gameId?: number | null; platform?: string; titleId?: string; personId?: number | null },
  ): Promise<GamePage> {
    return this.get<GamePage>(initData, "/game", {
      game_id: ref.gameId ?? undefined,
      platform: ref.gameId ? undefined : ref.platform,
      title_id: ref.gameId ? undefined : ref.titleId,
      person: ref.personId ?? undefined,
    });
  }

  setFavorite(
    initData: string,
    gameId: number,
    on: boolean,
  ): Promise<{ ok: boolean; favorite: boolean; favorites: number }> {
    return on
      ? this.put(initData, `/game/${gameId}/favorite`)
      : this.delete(initData, `/game/${gameId}/favorite`);
  }

  searchGames(initData: string, q: string): Promise<{ ok: boolean; games: GameCard[] }> {
    return this.get(initData, "/game-search", { q });
  }

  favorites(initData: string, personId?: number | null): Promise<{ ok: boolean; games: GameCard[] }> {
    return this.get(initData, "/game-favorites", { person: personId ?? undefined });
  }
}

export const gameApi = new GameApi();
