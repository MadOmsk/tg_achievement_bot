# The sign-in code sent by email (services/email_login.py, #162). Plain text,
# no markup: it is the whole message.
email-code-subject = Your sign-in code: { $code }
email-code-body =
    Your code to sign in to Achievement Bot: { $code }

    It works for { $minutes } { $minutes ->
        [one] minute
       *[other] minutes
    }. If you did not try to sign in, just ignore this email.
