import { useEffect, useRef } from "react";

export type TelegramUser = Record<string, string | number>;

declare global {
  interface Window {
    onTelegramLogin?: (user: TelegramUser) => void;
  }
}

/** Telegram's own Login Widget (#157): it hands the page a signed identity the
 * server checks with the bot token. Used to sign in from a plain browser, and to
 * add Telegram to a person who signed in by email (#162). The widget renders
 * only on a domain set with BotFather's /setdomain. */
export function TelegramLogin({ bot, onAuth }: { bot: string; onAuth: (user: TelegramUser) => void }) {
  const holder = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!holder.current) return;
    window.onTelegramLogin = onAuth;
    const script = document.createElement("script");
    script.async = true;
    script.src = "https://telegram.org/js/telegram-widget.js?22";
    script.setAttribute("data-telegram-login", bot);
    script.setAttribute("data-size", "large");
    script.setAttribute("data-radius", "14");
    script.setAttribute("data-userpic", "false");
    script.setAttribute("data-onauth", "onTelegramLogin(user)");
    holder.current.appendChild(script);
    const node = holder.current;
    return () => {
      node.innerHTML = "";
      delete window.onTelegramLogin;
    };
  }, [bot, onAuth]);

  return <div ref={holder} className="telegram-login" />;
}
