import { BaseApi, WEB_SESSION } from "../base/baseApi";
import { API_BASE_ROUTES, USER_ROUTES } from "../../components/shared/constants/routes";
import type {
  InvitesResponse,
  AccountPlatform,
  ChatPatchBody,
  ChatRow,
  LoginsResponse,
  MergeChoices,
  MergePreview,
  MeResponse,
  UserSettingsPatch,
  PasskeysResponse,
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
  authConfig(): Promise<{
    bot_username: string | null;
    bot_id?: number | null;
    email?: boolean;
    passkey?: boolean;
  }> {
    return this.get(WEB_SESSION, "/auth/config");
  }

  /** `invite`: somebody new signs up only with one (owner, 2026-10-05). */
  loginTelegram(user: Record<string, string | number>, invite?: string | null): Promise<{ ok: boolean }> {
    return this.post(WEB_SESSION, "/auth/telegram", invite ? { ...user, invite } : user);
  }

  /** Finish a sign-up that waited for its invite (`signup` from the refusal). */
  signUp(signup: string, invite: string): Promise<{ ok: boolean }> {
    return this.post(WEB_SESSION, "/auth/signup", { signup, invite });
  }

  invites(initData: string): Promise<InvitesResponse> {
    return this.get(initData, "/me/invites");
  }

  createInvite(initData: string): Promise<{ code: string }> {
    return this.post(initData, "/me/invites");
  }

  deleteInvite(initData: string, code: string): Promise<{ ok: boolean }> {
    return this.request(initData, `/me/invites/${encodeURIComponent(code)}`, { method: "DELETE" });
  }

  /** Email sign-in (#162): a code to the address, then the code back. */
  /** A new address brings its invite: the server checks it before mailing.
   * `passkey`: this browser can use a key — an address with one is answered
   * with the key's options instead of a mailed code. */
  emailSignInStart(
    email: string,
    locale: string,
    invite?: string | null,
    passkey?: boolean,
  ): Promise<
    | { ok: boolean; resend_after: number; skip_code?: boolean; passkey?: undefined }
    | { passkey: true; token: string; options: Record<string, unknown> }
  > {
    return this.post(WEB_SESSION, "/auth/email/start", {
      email,
      locale,
      ...(invite ? { invite } : {}),
      ...(passkey !== undefined ? { passkey } : {}),
    });
  }

  /** Passkeys (owner, 2026-10-08). */
  passkeys(initData: string): Promise<PasskeysResponse> {
    return this.get(initData, "/me/passkeys");
  }

  passkeyOptions(initData: string): Promise<{ token: string; options: Record<string, unknown> }> {
    return this.post(initData, "/me/passkeys/options", {});
  }

  addPasskey(initData: string, token: string, credential: Record<string, unknown>): Promise<PasskeysResponse> {
    return this.post(initData, "/me/passkeys", { token, credential });
  }

  removePasskey(initData: string, id: string): Promise<PasskeysResponse> {
    return this.delete(initData, `/me/passkeys/${encodeURIComponent(id)}`);
  }

  passkeySignIn(token: string, credential: Record<string, unknown>): Promise<{ ok: boolean }> {
    return this.post(WEB_SESSION, "/auth/passkey/verify", { token, credential });
  }

  emailSignInVerify(
    email: string,
    code: string,
    locale: string,
    invite?: string | null,
  ): Promise<{ ok: boolean }> {
    return this.post(WEB_SESSION, "/auth/email/verify", { email, code, locale, invite: invite || undefined });
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

  /** «Позже» on the app's one ask for an email. */
  emailLater(initData: string): Promise<{ ok: boolean }> {
    return this.post(initData, "/me/email/later");
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
