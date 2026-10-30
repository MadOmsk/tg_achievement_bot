import { BaseApi } from "../base/baseApi";
import { ADMIN_ROUTES, API_BASE_ROUTES } from "../../core/constants/routes";
import type {
  AdminAction,
  AdminActionStep,
  AdminChatAdmin,
  AdminChatRow,
  AdminHome,
  AdminKeys,
  AdminSetting,
  AdminSettings,
  AdminUserCard,
  AdminUserRow,
} from "./adminApiModels";

export type Role = "user" | "admin" | "superadmin";

export class AdminApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.ADMIN) {
    super(baseUrl);
  }

  /** A person's role (owner, 2026-10-28): the super-admin's to read and give. */
  fetchRole(initData: string, personId: number): Promise<{ role: Role; fixed: boolean }> {
    return this.get<{ role: Role; fixed: boolean }>(initData, ADMIN_ROUTES.ROLE(personId));
  }

  fetchHome(initData: string): Promise<AdminHome> {
    return this.get<AdminHome>(initData, ADMIN_ROUTES.HOME);
  }

  fetchKeys(initData: string): Promise<AdminKeys> {
    return this.get<AdminKeys>(initData, ADMIN_ROUTES.KEYS);
  }

  putKey(initData: string, name: string, value: string): Promise<AdminKeys> {
    return this.put<AdminKeys>(initData, ADMIN_ROUTES.KEY(name), { value });
  }

  deleteKey(initData: string, name: string): Promise<AdminKeys> {
    return this.delete<AdminKeys>(initData, ADMIN_ROUTES.KEY(name));
  }

  fetchSettings(initData: string): Promise<AdminSettings> {
    return this.get<AdminSettings>(initData, ADMIN_ROUTES.SETTINGS);
  }

  patchSetting(initData: string, key: string, value: AdminSetting["value"]): Promise<AdminSettings> {
    return this.patch<AdminSettings>(initData, ADMIN_ROUTES.SETTINGS, { key, value });
  }

  fetchUsers(
    initData: string,
  ): Promise<{ users: AdminUserRow[]; chats: Array<{ chat_id: number; title: string | null }> }> {
    return this.get(initData, ADMIN_ROUTES.USERS);
  }

  fetchUser(initData: string, personId: number): Promise<AdminUserCard> {
    return this.get<AdminUserCard>(initData, ADMIN_ROUTES.USER(personId));
  }

  fetchActions(
    initData: string,
    scope: "user" | "chat" | "global",
    target: string,
  ): Promise<{ actions: AdminAction[] }> {
    const query = `?scope=${scope}&target=${encodeURIComponent(target)}`;
    return this.get<{ actions: AdminAction[] }>(initData, `${ADMIN_ROUTES.ACTIONS}${query}`);
  }

  postAction(
    initData: string,
    body: { scope: AdminAction["scope"]; target: string; action: string; step: number },
  ): Promise<AdminActionStep> {
    return this.post<AdminActionStep>(initData, ADMIN_ROUTES.ACTIONS, body);
  }

  fetchChats(initData: string): Promise<{ chats: AdminChatRow[] }> {
    return this.get<{ chats: AdminChatRow[] }>(initData, ADMIN_ROUTES.CHATS);
  }

  fetchChatSettings(initData: string, chatId: number): Promise<AdminSettings> {
    return this.get<AdminSettings>(initData, ADMIN_ROUTES.CHAT_SETTINGS(chatId));
  }

  patchChatSetting(
    initData: string,
    chatId: number,
    key: string,
    value: AdminSetting["value"],
  ): Promise<AdminSettings> {
    return this.patch<AdminSettings>(initData, ADMIN_ROUTES.CHAT_SETTINGS(chatId), { key, value });
  }

  /** A chat's admin and who the role may go to (#232). */
  fetchChatAdmin(initData: string, chatId: number): Promise<AdminChatAdmin> {
    return this.get<AdminChatAdmin>(initData, ADMIN_ROUTES.CHAT_ADMIN(chatId));
  }

  /** Appoints (an app admin) or hands the role on (the chat admin, who loses it: `still` false). */
  putChatAdmin(initData: string, chatId: number, tgId: number): Promise<{ ok: boolean; still: boolean }> {
    return this.put<{ ok: boolean; still: boolean }>(initData, ADMIN_ROUTES.CHAT_ADMIN(chatId), { tg_id: tgId });
  }

  deleteChatAdmin(initData: string, chatId: number): Promise<AdminChatAdmin> {
    return this.delete<AdminChatAdmin>(initData, ADMIN_ROUTES.CHAT_ADMIN(chatId));
  }

}

export const adminApi = new AdminApi();
