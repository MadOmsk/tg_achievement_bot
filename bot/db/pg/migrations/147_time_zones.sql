-- A person's and a chat's time zone by place (owner, 2026-10-30): an IANA
-- name, so a summer clock change follows by itself (Vilnius is UTC+2 in
-- winter, UTC+3 in summer). `tz_offset_min` stays, read only where no name
-- is set. Every offset kept before becomes a zone that keeps the very same
-- clock: Russia's own by their cities (no clock changes there since 2014),
-- the rest the fixed `Etc/GMT` zone of that offset (its sign is reversed by
-- the standard: UTC+2 is `Etc/GMT-2`). A half-hour offset stays an offset.
ALTER TABLE user_settings ADD COLUMN IF NOT EXISTS tz_name TEXT;
ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS tz_name TEXT;

UPDATE user_settings SET tz_name = CASE tz_offset_min
    WHEN 120 THEN 'Europe/Kaliningrad'
    WHEN 180 THEN 'Europe/Moscow'
    WHEN 240 THEN 'Europe/Samara'
    WHEN 300 THEN 'Asia/Yekaterinburg'
    WHEN 360 THEN 'Asia/Omsk'
    WHEN 420 THEN 'Asia/Novosibirsk'
    WHEN 480 THEN 'Asia/Irkutsk'
    WHEN 540 THEN 'Asia/Yakutsk'
    WHEN 600 THEN 'Asia/Vladivostok'
    WHEN 660 THEN 'Asia/Magadan'
    WHEN 720 THEN 'Asia/Kamchatka'
    ELSE CASE WHEN tz_offset_min % 60 = 0 AND tz_offset_min BETWEEN -720 AND 840
        THEN 'Etc/GMT' || CASE WHEN tz_offset_min > 0 THEN '-' || (tz_offset_min / 60)
                               WHEN tz_offset_min < 0 THEN '+' || (-tz_offset_min / 60)
                               ELSE '' END
        END
    END
WHERE tz_offset_min IS NOT NULL AND tz_name IS NULL;

UPDATE chat_settings SET tz_name = CASE tz_offset_min
    WHEN 120 THEN 'Europe/Kaliningrad'
    WHEN 180 THEN 'Europe/Moscow'
    WHEN 240 THEN 'Europe/Samara'
    WHEN 300 THEN 'Asia/Yekaterinburg'
    WHEN 360 THEN 'Asia/Omsk'
    WHEN 420 THEN 'Asia/Novosibirsk'
    WHEN 480 THEN 'Asia/Irkutsk'
    WHEN 540 THEN 'Asia/Yakutsk'
    WHEN 600 THEN 'Asia/Vladivostok'
    WHEN 660 THEN 'Asia/Magadan'
    WHEN 720 THEN 'Asia/Kamchatka'
    ELSE CASE WHEN tz_offset_min % 60 = 0 AND tz_offset_min BETWEEN -720 AND 840
        THEN 'Etc/GMT' || CASE WHEN tz_offset_min > 0 THEN '-' || (tz_offset_min / 60)
                               WHEN tz_offset_min < 0 THEN '+' || (-tz_offset_min / 60)
                               ELSE '' END
        END
    END
WHERE tz_name IS NULL;
