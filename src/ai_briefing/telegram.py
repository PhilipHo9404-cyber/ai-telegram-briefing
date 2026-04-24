from __future__ import annotations

from html import escape
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import DailyBrief


def format_brief_markdown(brief: DailyBrief) -> str:
    lines = [f"<b>{escape(brief.brief_title)}</b>", "", f"{escape(brief.summary_intro)}", ""]

    for index, item in enumerate(brief.items, start=1):
        lines.extend(
            [
                f"<b>{index}. {escape(item.title)}</b>",
                f"摘要: {escape(item.summary)}",
                f"商业意义: {escape(item.business_angle)}",
                f"来源: {escape(item.source_name)} | {escape(item.published_at)}",
                f'<a href="{escape(item.source_url, quote=True)}">原文链接</a>',
                "",
            ]
        )

    if brief.signals:
        lines.append("<b>今日信号</b>")
        for signal in brief.signals:
            lines.append(f"- {escape(signal)}")

    return "\n".join(lines).strip()


def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    body = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    request = Request(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(body).encode("utf-8"),
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram API error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Telegram API network error: {exc.reason}") from exc

    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API rejected request: {payload}")
