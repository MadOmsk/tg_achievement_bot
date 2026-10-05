# The sign-in code sent by email (services/email_login.py, #162). Plain text,
# no markup: it is the whole message.
email-code-subject = Код для входа: { $code }
email-code-body =
    Твой код для входа в Unlocked: { $code }

    Он действует { $minutes } { $minutes ->
        [one] минуту
        [few] минуты
       *[many] минут
    }. Если ты не пытался войти, просто не обращай внимания на это письмо.
