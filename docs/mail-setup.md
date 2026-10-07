# Setting up mail on the server

For whoever deploys Unlocked on the VPS. Half an hour to an hour, mostly waiting for DNS.

## What it is for

Unlocked sends one kind of email: the six-digit code to sign in by email. Until mail is set up:

- the browser's sign-in screen offers Telegram only, with no email field;
- **nobody new can sign up in a browser at all**: signing up takes an email, or Telegram plus an invite code;
- the "Add your email" screen is never shown.

The bot, the Mini App inside Telegram and everything else work without it.

## 1. Pick a way to send

Any SMTP server will do. The volume is tiny: a few dozen messages a day for a community of 20–30.

| Option | When | Downsides |
|---|---|---|
| **An email service** — [Brevo](https://www.brevo.com) (300 a day free), [Resend](https://resend.com), [Mailgun](https://www.mailgun.com), Amazon SES | **Recommended for production.** Mail from your own domain, good delivery. | The domain has to be verified through DNS. |
| **A mailbox** — Gmail, Yandex, Mail.ru with an app password | Quick; fine for the test server. | The sender is that mailbox; daily limits; a personal password on the server. |
| **Your own Postfix on the VPS** | Not advised. | Hosts often block port 25, and a fresh IP has no reputation — mail lands in spam. |

The steps below use a service. For a mailbox, skip step 2 and take its SMTP details from its help (Gmail: `smtp.gmail.com`, 587, an app password from Google's security settings).

## 2. Verify the domain

1. Sign up with the service and add the domain mail will come from: `sultanpharm.com`, or a subdomain such as `mail.sultanpharm.com`.
2. The service shows DNS records. Add them wherever the domain's DNS lives (the registrar — Spaceship/Namecheap — or Cloudflare):
   - **SPF** — a TXT record `v=spf1 include:… ~all`. If the domain already has an SPF record, add the `include:…` to it instead of creating a second one: two SPF records break both.
   - **DKIM** — one or more TXT or CNAME records named like `xxx._domainkey`.
   - **DMARC** — a TXT record on `_dmarc`, `v=DMARC1; p=none;`, unless the service gives its own.
3. Wait until the service says "verified": minutes to a couple of hours.

## 3. Get the SMTP details

Create an SMTP key in the service (often under "SMTP & API"). You need:

- the host, e.g. `smtp-relay.brevo.com`;
- the port: **587** (STARTTLS) or **465** (SSL);
- the login and the password (the SMTP key).

Check the VPS can reach that port:

```bash
timeout 5 bash -c '</dev/tcp/smtp-relay.brevo.com/587' && echo open || echo closed
```

If `closed`, try 465, or ask the host whether outgoing SMTP is blocked.

## 4. Put the settings in `.env`

Each bot reads its own environment file:

| | production | test server |
|---|---|---|
| file | `/opt/xbox_achievement_bot/.env` | `/opt/xbox_bot_test/.env.test` |
| unit | `xbox-bot` | `xbox-bot-test` |

Edit it as the bot's user, never as root:

```bash
sudo -u botsvc nano /opt/xbox_achievement_bot/.env
```

```ini
SMTP_HOST=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_SECURITY=starttls        # starttls for 587, ssl for 465
SMTP_USERNAME=login-from-the-service
SMTP_PASSWORD=key-from-the-service
SMTP_FROM=no-reply@sultanpharm.com

# Development only. On a server: false, or no line at all.
EMAIL_LOG_CODES=false
EMAIL_SKIP_CODE=false
```

Mind that:

- **`SMTP_FROM` is a bare address**, no display name ("Unlocked <…>" will not do): it is also the contact given to the push services. It must be on the verified domain — or, for a mailbox, the mailbox itself.
- Without `SMTP_HOST` **or** `SMTP_FROM`, mail counts as off.
- The password lives in `.env` only. It is not in GitHub or CI: the deploy never touches the environment file.
- Push also needs `MINI_APP_URL`, already set if the Mini App works.

## 5. Restart and check

```bash
sudo systemctl restart xbox-bot          # xbox-bot-test for the test server
journalctl -u xbox-bot -n 50 --no-pager  # the bot is up, no mail errors
curl -s https://xbox.sultanpharm.com/api/mini/auth/config
```

The answer must say `"email": true`. Then open the Mini App in a private browser window and type your address — the code should arrive within seconds. Check it did not land in spam: [mail-tester.com](https://www.mail-tester.com) shows whether SPF and DKIM are right.

## When it does not work

| What you see | What to do |
|---|---|
| `"email": false` | `SMTP_HOST` or `SMTP_FROM` is empty, the wrong file was edited, or the bot was not restarted. |
| "Could not send" in the app, `sign-in code not sent: …` in the log | Read the error: `535`/`Authentication` is a wrong login or key; a timeout is a blocked port (step 3) — try 465 with `SMTP_SECURITY=ssl`. |
| Mail goes to spam | The domain is not fully verified: check SPF, DKIM and DMARC on mail-tester. |
| `EMAIL_SKIP_CODE is ignored` in the log | Remove `EMAIL_SKIP_CODE` from `.env`: on a server it does nothing but this warning. |

To change the key, put the new one in `.env` and restart the unit.
