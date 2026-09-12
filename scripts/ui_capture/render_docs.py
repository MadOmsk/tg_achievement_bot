"""Captured API payloads -> the markdown that goes into docs/ui/.

One block per screen: what triggers it, the text exactly as Telegram would
receive it, the inline keyboard laid out row by row, and any photo or media
group with its own URL.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SENT = {"SendMessage", "SendPhoto", "SendMediaGroup", "EditMessageText", "EditMessageCaption"}
METHOD_LABEL = {
    "SendMessage": "сообщение",
    "SendPhoto": "фото с подписью",
    "SendMediaGroup": "галерея",
    "EditMessageText": "правка того же сообщения",
    "EditMessageCaption": "правка подписи",
    "AnswerCallbackQuery": "всплывашка",
    "DeleteMessage": "удаление сообщения",
    "PinChatMessage": "закрепление",
}


def keyboard_lines(markup: dict[str, Any] | None) -> list[str]:
    if not markup or "inline_keyboard" not in markup:
        return []
    lines = []
    for row in markup["inline_keyboard"]:
        buttons = []
        for button in row:
            label = button.get("text", "")
            if button.get("url"):
                buttons.append(f"[ {label} ]→ссылка")
            else:
                buttons.append(f"[ {label} ]")
        lines.append("  ".join(buttons))
    return lines


def render(screen: dict[str, Any]) -> str:
    out = [f"### {screen['title']}", ""]
    trigger = screen["input"]
    out.append(f"`{screen['id']}` · вход: `{trigger}` · {screen['scope']}")
    out.append("")
    if screen.get("error"):
        out.append(f"> ⚠️ **Экран не построился:** `{screen['error']}`")
        out.append("")
        return "\n".join(out)

    sent = [call for call in screen["calls"] if call["method"] in SENT]
    if not sent:
        others = ", ".join(
            f"{METHOD_LABEL.get(call['method'], call['method'])}"
            + (f" «{call['payload']['text']}»" if call["payload"].get("text") else "")
            for call in screen["calls"]
        )
        out.append(f"Ничего не рисует — только {others or 'тишина'}.")
        out.append("")
        return "\n".join(out)

    for index, call in enumerate(sent):
        payload = call["payload"]
        parts = [METHOD_LABEL.get(call["method"], call["method"])]
        if payload.get("photo"):
            parts.append(f"картинка: {payload['photo']}")
        if payload.get("media"):
            urls = [item.get("media") for item in payload["media"]]
            parts.append(f"{len(urls)} картинк(и): " + ", ".join(str(u) for u in urls))
        if len(sent) > 1:
            out.append(f"**{index + 1}. {' · '.join(parts)}**")
        elif len(parts) > 1:
            out.append(f"**{' · '.join(parts[1:])}**")
        # A media group carries its caption on the first item, not on the call.
        media_caption = ""
        if payload.get("media"):
            media_caption = payload["media"][0].get("caption") or ""
        text = payload.get("text") or payload.get("caption") or media_caption
        if text:
            out.append("")
            out.append("```")
            out.extend(text.split("\n"))
            out.append("```")
        rows = keyboard_lines(payload.get("reply_markup"))
        if rows:
            out.append("")
            out.append("```")
            out.extend(rows)
            out.append("```")
        out.append("")

    extra = [call for call in screen["calls"] if call["method"] not in SENT]
    for call in extra:
        label = METHOD_LABEL.get(call["method"], call["method"])
        text = call["payload"].get("text")
        if call["method"] == "AnswerCallbackQuery" and not text:
            continue  # the silent ack every callback ends with
        note = f"— «{text}»" if text else ""
        alert = " (модальное окно)" if call["payload"].get("show_alert") else ""
        out.append(f"Плюс {label}{alert} {note}".rstrip())
        out.append("")
    return "\n".join(out)


def main() -> None:
    screens: list[dict[str, Any]] = []
    for path in sys.argv[2:]:
        screens.extend(json.loads(Path(path).read_text(encoding="utf-8")))
    Path(sys.argv[1]).write_text("\n".join(render(screen) for screen in screens), encoding="utf-8")
    broken = [s["id"] for s in screens if s.get("error")]
    print(f"{len(screens)} screens rendered, {len(broken)} broken: {broken}")


main()
