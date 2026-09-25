// Base
export { BaseApi } from "./base/baseApi";

// User API
export * from "./user/userApiModels";
export { UserApi, userApi } from "./user/userApi";

// Club API
export * from "./club/clubApiModels";
export { ClubApi, clubApi } from "./club/clubApi";

// Games API
export * from "./games/gamesApiModels";
export { GamesApi, gamesApi } from "./games/gamesApi";

// Admin API
export * from "./admin/adminApiModels";
export { AdminApi, adminApi } from "./admin/adminApi";

// HLTB API
export * from "./hltb/hltbApiModels";
export { HltbApi, hltbApi } from "./hltb/hltbApi";

// Functional aliases for backward compatibility with existing components
import { userApi } from "./user/userApi";
import { clubApi } from "./club/clubApi";
import { gamesApi } from "./games/gamesApi";
import { adminApi } from "./admin/adminApi";
import { hltbApi } from "./hltb/hltbApi";

export const fetchMe = (initData: string) => userApi.fetchMe(initData);
export const fetchAvatarBlob = (initData: string, tgId: number) => userApi.fetchAvatarBlob(initData, tgId);
export const patchSettings = (...args: Parameters<typeof userApi.patchSettings>) => userApi.patchSettings(...args);
export const connectXbox = (initData: string) => userApi.connectXbox(initData);
export const disconnectXbox = (initData: string) => userApi.disconnectXbox(initData);
export const connectSteam = (...args: Parameters<typeof userApi.connectSteam>) => userApi.connectSteam(...args);
export const disconnectSteam = (initData: string) => userApi.disconnectSteam(initData);
export const connectPsn = (...args: Parameters<typeof userApi.connectPsn>) => userApi.connectPsn(...args);
export const disconnectPsn = (initData: string) => userApi.disconnectPsn(initData);
export const syncXbox = (initData: string) => userApi.syncXbox(initData);
export const patchChat = (...args: Parameters<typeof userApi.patchChat>) => userApi.patchChat(...args);

export const fetchFeed = (...args: Parameters<typeof clubApi.fetchFeed>) => clubApi.fetchFeed(...args);
export const fetchOnline = (...args: Parameters<typeof clubApi.fetchOnline>) => clubApi.fetchOnline(...args);
export const fetchSummary = (...args: Parameters<typeof clubApi.fetchSummary>) => clubApi.fetchSummary(...args);
export const fetchPerson = (...args: Parameters<typeof clubApi.fetchPerson>) => clubApi.fetchPerson(...args);

export const fetchGame = (...args: Parameters<typeof gamesApi.fetchGame>) => gamesApi.fetchGame(...args);

export const fetchAdminHome = (initData: string) => adminApi.fetchHome(initData);
export const fetchAdminKeys = (initData: string) => adminApi.fetchKeys(initData);
export const putAdminKey = (...args: Parameters<typeof adminApi.putKey>) => adminApi.putKey(...args);
export const deleteAdminKey = (...args: Parameters<typeof adminApi.deleteKey>) => adminApi.deleteKey(...args);
export const fetchAdminLimits = (initData: string) => adminApi.fetchLimits(initData);
export const patchAdminLimit = (...args: Parameters<typeof adminApi.patchLimit>) => adminApi.patchLimit(...args);
export const fetchAdminDefaults = (initData: string) => adminApi.fetchDefaults(initData);
export const patchAdminDefaults = (...args: Parameters<typeof adminApi.patchDefaults>) => adminApi.patchDefaults(...args);
export const fetchAdminUsers = (initData: string) => adminApi.fetchUsers(initData);
export const fetchAdminUser = (...args: Parameters<typeof adminApi.fetchUser>) => adminApi.fetchUser(...args);
export const patchAdminUser = (...args: Parameters<typeof adminApi.patchUser>) => adminApi.patchUser(...args);
export const fetchAdminChats = (initData: string) => adminApi.fetchChats(initData);
export const patchAdminChat = (...args: Parameters<typeof adminApi.patchChat>) => adminApi.patchChat(...args);
export const postAdminChatAction = (...args: Parameters<typeof adminApi.postChatAction>) => adminApi.postChatAction(...args);

export const searchHltb = (...args: Parameters<typeof hltbApi.search>) => hltbApi.search(...args);
export const resolveHltb = (...args: Parameters<typeof hltbApi.resolve>) => hltbApi.resolve(...args);
