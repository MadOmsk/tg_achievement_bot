import { BaseApi, WEB_SESSION } from "../base/baseApi";
import { API_BASE_ROUTES, USER_ROUTES } from "../../components/shared/constants/routes";
import type {
  AccountPlatform,
  ChatPatchBody,
  ChatRow,
  LoginsResponse,
  MergeChoices,
  MergePreview,
  MeResponse,
  UserSettingsPatch,
} from "./userApiModels";

export class UserApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.MINI) {
    super(baseUrl);
  }

  fetchMe(initData: string): Promise<MeResponse> {
    return this.get<MeResponse>(initData, USER_ROUTES.ME);
  }

  async fetchAvatarBlob(initData: string, personId: number): Promise<Blob | null> {
    const url = this.buildUrl(USER_ROUTES.AVATAR(personId));
    const response = await fetch(url, {
      headers: this.initHeaders(initData),
    });
    if (!response.ok) return null;
    return response.blob();
  }

  /** The bot a browser's Telegram Login Widget belongs to (#157), and whether
   * a mail server is set up for email sign-in (#162). */
  authConfig(): Promise<{ bot_username: string | null; email?: boolean }> {
    return this.get(WEB_SESSION, "/auth/config");
  }

  loginTelegram(user: Record<string, string | number>): Promise<{ ok: boolean }> {
    return this.post(WEB_SESSION, "/auth/telegram", user);
  }

  /** Email sign-in (#162): a code to the address, then the code back. */
  emailSignInStart(
    email: string,
    locale: string,
  ): Promise<{ ok: boolean; resend_after: number; skip_code?: boolean }> {
    return this.post(WEB_SESSION, "/auth/email/start", { email, locale });
  }

  emailSignInVerify(email: string, code: string, locale: string): Promise<{ ok: boolean }> {
    return this.post(WEB_SESSION, "/auth/email/verify", { email, code, locale });
  }

  logins(initData: string): Promise<LoginsResponse> {
    return this.get(initData, "/me/logins");
  }

  emailLinkStart(
    initData: string,
    email: string,
  ): Promise<{ ok: boolean; resend_after: number; skip_code?: boolean }> {
    return this.post(initData, "/me/email/start", { email });
  }

  emailLinkVerify(initData: string, email: string, code: string): Promise<LoginsResponse> {
    return this.post(initData, "/me/email/verify", { email, code });
  }

  /** A t.me link that adds Telegram by writing to the bot from it. */
  telegramLinkUrl(initData: string): Promise<{ url: string }> {
    return this.get(initData, "/me/telegram/link");
  }

  pendingMerge(initData: string): Promise<{ merge: MergePreview | null }> {
    return this.get(initData, "/me/merge");
  }

  merge(initData: string, choices: MergeChoices): Promise<LoginsResponse> {
    return this.post(initData, "/me/merge", { choices });
  }

  cancelMerge(initData: string): Promise<{ ok: boolean }> {
    return this.delete(initData, "/me/merge");
  }

  removeTelegram(initData: string): Promise<LoginsResponse> {
    return this.delete(initData, "/me/telegram");
  }

  linkTelegram(initData: string, user: Record<string, string | number>): Promise<LoginsResponse> {
    return this.post(initData, "/me/telegram", user);
  }

  logout(): Promise<{ ok: boolean }> {
    return this.post(WEB_SESSION, "/auth/logout");
  }

  deleteAccount(initData: string): Promise<{ ok: boolean }> {
    return this.delete<{ ok: boolean }>(initData, USER_ROUTES.DELETE_ME);
  }

  patchSettings(initData: string, body: UserSettingsPatch): Promise<MeResponse> {
    return this.patch<MeResponse>(initData, USER_ROUTES.SETTINGS, body);
  }

  /** Set one's own picture: the bytes of an image already cropped and shrunk. */
  async putAvatar(initData: string, image: Blob): Promise<MeResponse> {
    const headers: Record<string, string> = { "Content-Type": image.type || "image/jpeg" };
    if (initData !== WEB_SESSION) headers["X-Telegram-Init-Data"] = initData;
    const response = await fetch(this.buildUrl(USER_ROUTES.AVATAR_ME), {
      method: "PUT",
      headers,
      body: image,
    });
    if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
    return (await response.json()) as MeResponse;
  }

  deleteAvatar(initData: string): Promise<MeResponse> {
    return this.delete<MeResponse>(initData, USER_ROUTES.AVATAR_ME);
  }

  putHandle(initData: string, handle: string): Promise<MeResponse> {
    return this.put<MeResponse>(initData, USER_ROUTES.HANDLE, { handle });
  }

  confirmHandle(initData: string): Promise<MeResponse> {
    return this.post<MeResponse>(initData, USER_ROUTES.CONFIRM_HANDLE);
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

  /** Every PSN account, or the one `accountId` names (#10). */
  disconnectPsn(initData: string, accountId?: string): Promise<{ ok: boolean }> {
    return this.post<{ ok: boolean }>(
      initData,
      USER_ROUTES.DISCONNECT_PSN,
      accountId ? { account_id: accountId } : {},
    );
  }

  /** The owner's switch for a platform's posts (#20), or for one of its PSN
   * accounts when `accountId` is given (#10). */
  setAccountPublishes(
    initData: string,
    platform: AccountPlatform,
    publishes: boolean,
    accountId?: string,
  ): Promise<MeResponse> {
    return this.patch<MeResponse>(
      initData,
      USER_ROUTES.ACCOUNT(platform),
      accountId ? { publishes, account_id: accountId } : { publishes },
    );
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
