/// <reference types="vite/client" />

type TelegramWebApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  disableVerticalSwipes?: () => void;
  openLink: (url: string) => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  themeParams: Record<string, string>;
  colorScheme: string;
  initDataUnsafe?: {
    start_param?: string;
    user?: { photo_url?: string; first_name?: string; username?: string };
  };
};

interface Window {
  Telegram?: {
    WebApp?: TelegramWebApp;
  };
}
