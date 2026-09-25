import { BaseApi } from "../base/baseApi";
import { ADMIN_ROUTES, API_BASE_ROUTES } from "../../components/shared/constants/routes";
import type {
  AdminChatRow,
  AdminDefaults,
  AdminHome,
  AdminKeys,
  AdminLimit,
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

  fetchLimits(initData: string): Promise<{ items: AdminLimit[] }> {
    return this.get<{ items: AdminLimit[] }>(initData, ADMIN_ROUTES.LIMITS);
  }

  patchLimit(initData: string, key: string, value: number): Promise<{ items: AdminLimit[] }> {
    return this.patch<{ items: AdminLimit[] }>(initData, ADMIN_ROUTES.LIMITS, { key, value });
  }

  fetchDefaults(initData: string): Promise<AdminDefaults> {
    return this.get<AdminDefaults>(initData, ADMIN_ROUTES.DEFAULTS);
  }

  patchDefaults(initData: string, body: Partial<AdminDefaults>): Promise<AdminDefaults> {
    return this.patch<AdminDefaults>(initData, ADMIN_ROUTES.DEFAULTS, body);
  }

  fetchUsers(
    initData: string,
  ): Promise<{ users: AdminUserRow[]; chats: Array<{ chat_id: number; title: string | null }> }> {
    return this.get(initData, ADMIN_ROUTES.USERS);
  }

  fetchUser(initData: string, tgId: number): Promise<AdminUserCard> {
    return this.get<AdminUserCard>(initData, ADMIN_ROUTES.USER(tgId));
  }

  patchUser(initData: string, tgId: number, body: Record<string, unknown>): Promise<AdminUserCard> {
    return this.patch<AdminUserCard>(initData, ADMIN_ROUTES.USER(tgId), body);
  }

  fetchChats(initData: string): Promise<{ chats: AdminChatRow[] }> {
    return this.get<{ chats: AdminChatRow[] }>(initData, ADMIN_ROUTES.CHATS);
  }

  patchChat(initData: string, chatId: number, body: Record<string, unknown>): Promise<AdminChatRow> {
    return this.patch<AdminChatRow>(initData, ADMIN_ROUTES.CHAT(chatId), body);
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
