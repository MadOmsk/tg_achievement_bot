"""Captured API payloads -> the markdown that goes into docs/ui/.

One block per screen: what triggers it, the text exactly as Telegram would
receive it, the inline keyboard laid out row by row, and any photo or media
group with its own URL.

Prose here is English like everything else written in this project; the only
Russian in the output is what the bot's own locale files produced.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

SENT = {"SendMessage", "SendPhoto", "SendMediaGroup", "EditMessageText", "EditMessageCaption"}
METHOD_LABEL = {
    "SendMessage": "text message",
    "SendPhoto": "photo with a caption",
    "SendMediaGroup": "gallery",
    "EditMessageText": "edits the same message",
    "EditMessageCaption": "edits the caption",
    "AnswerCallbackQuery": "toast",
    "DeleteMessage": "deletes a message",
    "PinChatMessage": "pins the message",
}


def keyboard_lines(markup: dict[str, Any] | None) -> list[str]:
    if not markup or "inline_keyboard" not in markup:
        return []
    lines = []
    for row in markup["inline_keyboard"]:
        buttons = []
        for button in row:
            label = button.get("text", "")
            buttons.append(f"[ {label} ]→url" if button.get("url") else f"[ {label} ]")
        lines.append("  ".join(buttons))
    return lines


def render(screen: dict[str, Any]) -> str:
    out = [f"### {screen['title']}", ""]
    out.append(f"`{screen['id']}` · input: `{screen['input']}` · {screen['scope']}")
    out.append("")
    if screen.get("error"):
        out.append(f"> ⚠️ **This screen does not build:** `{screen['error']}`")
        out.append("")
        return "\n".join(out)

    sent = [call for call in screen["calls"] if call["method"] in SENT]
    if not sent:
        others = ", ".join(
            METHOD_LABEL.get(call["method"], call["method"])
            + (f" «{call['payload']['text']}»" if call["payload"].get("text") else "")
            for call in screen["calls"]
        )
        out.append(f"Draws nothing — only {others or 'silence'}.")
        out.append("")
        return "\n".join(out)

    for index, call in enumerate(sent):
        payload = call["payload"]
        parts = [METHOD_LABEL.get(call["method"], call["method"])]
        if payload.get("photo"):
            parts.append(f"image: {payload['photo']}")
        if payload.get("media"):
            urls = [item.get("media") for item in payload["media"]]
            parts.append(f"{len(urls)} image(s): " + ", ".join(str(url) for url in urls))
        if len(sent) > 1:
            out.append(f"**{index + 1}. {' · '.join(parts)}**")
        elif len(parts) > 1:
            out.append(f"**{' · '.join(parts)}**")
        # A media group carries its caption on the first item, not on the call.
        media_caption = payload["media"][0].get("caption") or "" if payload.get("media") else ""
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

    for call in [c for c in screen["calls"] if c["method"] not in SENT]:
        label = METHOD_LABEL.get(call["method"], call["method"])
        text = call["payload"].get("text")
        if call["method"] == "AnswerCallbackQuery" and not text:
            continue  # the silent ack every callback ends with
        alert = " (modal)" if call["payload"].get("show_alert") else ""
        out.append(f"Plus a {label}{alert}" + (f" — «{text}»" if text else ""))
        out.append("")
    return "\n".join(out)


def main() -> None:
    screens: list[dict[str, Any]] = []
    for path in sys.argv[2:]:
        screens.extend(json.loads(Path(path).read_text(encoding="utf-8")))
    Path(sys.argv[1]).write_text("\n".join(render(screen) for screen in screens), encoding="utf-8")
    broken = [screen["id"] for screen in screens if screen.get("error")]
    print(f"{len(screens)} screens rendered, {len(broken)} broken: {broken}")


main()
