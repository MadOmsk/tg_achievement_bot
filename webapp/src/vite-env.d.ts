/// <reference types="vite/client" />

type TelegramWebApp = {
  initData: string;
  ready: () => void;
  expand: () => void;
  close?: () => void;
  disableVerticalSwipes?: () => void;
  openLink: (url: string) => void;
  setHeaderColor?: (color: string) => void;
  setBackgroundColor?: (color: string) => void;
  themeParams: Record<string, string>;
  colorScheme: string;
  /** Telegram's own back arrow in the Mini App's header (Bot API 6.1+). */
  BackButton?: {
    show: () => void;
    hide: () => void;
    onClick: (callback: () => void) => void;
  };
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
