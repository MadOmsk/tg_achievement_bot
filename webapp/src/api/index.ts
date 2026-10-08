// Base
export { ApiError, BaseApi, WEB_SESSION } from "./base/baseApi";

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
export const fetchAvatarBlob = (initData: string, personId: number) =>
  userApi.fetchAvatarBlob(initData, personId);
export const patchSettings = (...args: Parameters<typeof userApi.patchSettings>) => userApi.patchSettings(...args);
export const logout = () => userApi.logout();
export const putAvatar = (initData: string, image: Blob) => userApi.putAvatar(initData, image);
export const deleteAvatar = (initData: string) => userApi.deleteAvatar(initData);
export const putHandle = (initData: string, handle: string) => userApi.putHandle(initData, handle);
export const confirmHandle = (initData: string) => userApi.confirmHandle(initData);
export const connectXbox = (initData: string) => userApi.connectXbox(initData);
export const disconnectXbox = (initData: string) => userApi.disconnectXbox(initData);
export const connectSteam = (...args: Parameters<typeof userApi.connectSteam>) => userApi.connectSteam(...args);
export const disconnectSteam = (initData: string) => userApi.disconnectSteam(initData);
export const connectPsn = (...args: Parameters<typeof userApi.connectPsn>) => userApi.connectPsn(...args);
export const deleteAccount = (initData: string) => userApi.deleteAccount(initData);
export const disconnectPsn = (...args: Parameters<typeof userApi.disconnectPsn>) =>
  userApi.disconnectPsn(...args);
export const setAccountPublishes = (...args: Parameters<typeof userApi.setAccountPublishes>) =>
  userApi.setAccountPublishes(...args);
export const syncXbox = (initData: string) => userApi.syncXbox(initData);
export const patchChat = (...args: Parameters<typeof userApi.patchChat>) => userApi.patchChat(...args);

export const fetchFeed = (...args: Parameters<typeof clubApi.fetchFeed>) => clubApi.fetchFeed(...args);
export const fetchNews = (...args: Parameters<typeof clubApi.fetchNews>) => clubApi.fetchNews(...args);
export const fetchOnline = (...args: Parameters<typeof clubApi.fetchOnline>) => clubApi.fetchOnline(...args);
export const fetchSummary = (...args: Parameters<typeof clubApi.fetchSummary>) => clubApi.fetchSummary(...args);
export const fetchPerson = (...args: Parameters<typeof clubApi.fetchPerson>) => clubApi.fetchPerson(...args);

export const fetchGame = (...args: Parameters<typeof gamesApi.fetchGame>) => gamesApi.fetchGame(...args);
export const fetchGameHltb = (...args: Parameters<typeof gamesApi.fetchGameHltb>) =>
  gamesApi.fetchGameHltb(...args);
export const fetchGameGuides = (...args: Parameters<typeof gamesApi.fetchGameGuides>) =>
  gamesApi.fetchGameGuides(...args);
export const fetchGamePatches = (...args: Parameters<typeof gamesApi.fetchGamePatches>) =>
  gamesApi.fetchGamePatches(...args);

export const fetchAdminHome = (initData: string) => adminApi.fetchHome(initData);
export const fetchAdminKeys = (initData: string) => adminApi.fetchKeys(initData);
export const putAdminKey = (...args: Parameters<typeof adminApi.putKey>) => adminApi.putKey(...args);
export const deleteAdminKey = (...args: Parameters<typeof adminApi.deleteKey>) => adminApi.deleteKey(...args);
export const fetchAdminSettings = (initData: string) => adminApi.fetchSettings(initData);
export const patchAdminSetting = (...args: Parameters<typeof adminApi.patchSetting>) => adminApi.patchSetting(...args);
export const fetchAdminChatSettings = (...args: Parameters<typeof adminApi.fetchChatSettings>) =>
  adminApi.fetchChatSettings(...args);
export const patchAdminChatSetting = (...args: Parameters<typeof adminApi.patchChatSetting>) =>
  adminApi.patchChatSetting(...args);
export const fetchAdminUsers = (initData: string) => adminApi.fetchUsers(initData);
export const fetchAdminUser = (...args: Parameters<typeof adminApi.fetchUser>) => adminApi.fetchUser(...args);
export const patchAdminUser = (...args: Parameters<typeof adminApi.patchUser>) => adminApi.patchUser(...args);
export const fetchAdminChats = (initData: string) => adminApi.fetchChats(initData);
export const postAdminChatAction = (...args: Parameters<typeof adminApi.postChatAction>) => adminApi.postChatAction(...args);

export const searchHltb = (...args: Parameters<typeof hltbApi.search>) => hltbApi.search(...args);
export const resolveHltb = (...args: Parameters<typeof hltbApi.resolve>) => hltbApi.resolve(...args);
