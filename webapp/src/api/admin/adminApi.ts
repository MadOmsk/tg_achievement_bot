import { BaseApi } from "../base/baseApi";
import { ADMIN_ROUTES, API_BASE_ROUTES } from "../../components/shared/constants/routes";
import type {
  AdminChatRow,
  AdminHome,
  AdminKeys,
  AdminSetting,
  AdminSettings,
  AdminUserCard,
  AdminUserRow,
} from "./adminApiModels";

export class AdminApi extends BaseApi {
  constructor(baseUrl: string = API_BASE_ROUTES.ADMIN) {
    super(baseUrl);
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

  patchUser(initData: string, personId: number, body: Record<string, unknown>): Promise<AdminUserCard> {
    return this.patch<AdminUserCard>(initData, ADMIN_ROUTES.USER(personId), body);
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

  postChatAction(
    initData: string,
    chatId: number,
    action: string,
  ): Promise<{ ok: boolean; deleted?: number; preview?: string | null }> {
    return this.post(initData, ADMIN_ROUTES.CHAT_ACTIONS(chatId), { action });
  }
}

export const adminApi = new AdminApi();
