import { BaseApi } from "../base/baseApi";
import { API_BASE_ROUTES, USER_ROUTES } from "../../components/shared/constants/routes";
import type { ChatPatchBody, ChatRow, MeResponse, UserSettingsPatch } from "./userApiModels";

export class UserApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.MINI) {
    super(baseUrl);
  }

  fetchMe(initData: string): Promise<MeResponse> {
    return this.get<MeResponse>(initData, USER_ROUTES.ME);
  }

  async fetchAvatarBlob(initData: string, tgId: number): Promise<Blob | null> {
    const url = this.buildUrl(USER_ROUTES.AVATAR(tgId));
    const response = await fetch(url, {
      headers: { "X-Telegram-Init-Data": initData },
    });
    if (!response.ok) return null;
    return response.blob();
  }

  deleteAccount(initData: string): Promise<{ ok: boolean }> {
    return this.delete<{ ok: boolean }>(initData, USER_ROUTES.DELETE_ME);
  }

  patchSettings(initData: string, body: UserSettingsPatch): Promise<MeResponse> {
    return this.patch<MeResponse>(initData, USER_ROUTES.SETTINGS, body);
  }

  connectXbox(initData: string): Promise<{ authorize_url: string }> {
    return this.post<{ authorize_url: string }>(initData, USER_ROUTES.CONNECT_XBOX);
  }

  disconnectXbox(initData: string): Promise<{ ok: boolean; revoke_url?: string }> {
    return this.post<{ ok: boolean; revoke_url?: string }>(initData, USER_ROUTES.DISCONNECT_XBOX);
  }

  connectSteam(
    initData: string,
    steamIdOrVanity: string,
  ): Promise<{ ok: boolean; profile_url?: string }> {
    return this.post<{ ok: boolean; profile_url?: string }>(initData, USER_ROUTES.CONNECT_STEAM, {
      steam_id: steamIdOrVanity,
    });
  }

  disconnectSteam(initData: string): Promise<{ ok: boolean }> {
    return this.post<{ ok: boolean }>(initData, USER_ROUTES.DISCONNECT_STEAM);
  }

  connectPsn(
    initData: string,
    onlineId: string,
  ): Promise<{ ok: boolean; profile_url?: string; needs_privacy_check?: boolean }> {
    return this.post<{ ok: boolean; profile_url?: string; needs_privacy_check?: boolean }>(
      initData,
      USER_ROUTES.CONNECT_PSN,
      { online_id: onlineId },
    );
  }

  disconnectPsn(initData: string): Promise<{ ok: boolean }> {
    return this.post<{ ok: boolean }>(initData, USER_ROUTES.DISCONNECT_PSN);
  }

  syncXbox(initData: string): Promise<{ ok: boolean; queued?: boolean; reason?: string }> {
    return this.post<{ ok: boolean; queued?: boolean; reason?: string }>(initData, USER_ROUTES.SYNC_XBOX);
  }

  patchChat(
    initData: string,
    chatId: number,
    body: ChatPatchBody,
  ): Promise<ChatRow | { ok: boolean }> {
    return this.patch<ChatRow | { ok: boolean }>(initData, USER_ROUTES.CHAT(chatId), body);
  }
}

export const userApi = new UserApi();
