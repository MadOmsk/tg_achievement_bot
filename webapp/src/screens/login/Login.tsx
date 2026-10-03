import { useEffect, useRef, useState } from "react";
import { userApi } from "../../api";
import { t, type Locale } from "../../i18n";
import "./Login.css";

type TelegramUser = Record<string, string | number>;

declare global {
  interface Window {
    onTelegramLogin?: (user: TelegramUser) => void;
  }
}

/** Sign-in for the Mini App opened in a plain browser (#157): Telegram's own Login
 * Widget, which hands the page a signed identity the server checks with the bot
 * token. WhatsApp will sit beside it. Inside Telegram this screen never shows. */
export function Login({ locale, onSignedIn }: { locale: Locale; onSignedIn: () => void }) {
  const holder = useRef<HTMLDivElement>(null);
  const [bot, setBot] = useState<string | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    userApi
      .authConfig()
      .then((res) => {
        if (!cancelled) setBot(res.bot_username);
      })
      .catch(() => {
        if (!cancelled) setBot(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!bot || !holder.current) return;
    window.onTelegramLogin = (user) => {
      setError(null);
      userApi
        .loginTelegram(user)
        .then(onSignedIn)
        .catch((err: unknown) => setError(String(err)));
    };
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
  }, [bot, onSignedIn]);

  return (
    <div className="login">
      <img className="login-mark" src="/logo.svg" alt="" width={96} height={96} />
      <h1>{t(locale, "loginTitle")}</h1>
      <p className="login-text">{t(locale, "loginText")}</p>
      {bot === null && <p className="login-text">{t(locale, "loginUnavailable")}</p>}
      <div ref={holder} className="login-widget" />
      {error && <p className="login-error">{error}</p>}
    </div>
  );
}
