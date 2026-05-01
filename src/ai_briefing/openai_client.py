from __future__ import annotations

import json
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .models import Article, BriefItem, DailyBrief, LLMConfig

BRIEF_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "brief_title": {"type": "string"},
        "summary_intro": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "business_angle": {"type": "string"},
                    "source_name": {"type": "string"},
                    "source_url": {"type": "string"},
                    "published_at": {"type": "string"},
                },
                "required": [
                    "title",
                    "summary",
                    "business_angle",
                    "source_name",
                    "source_url",
                    "published_at",
                ],
            },
        },
        "signals": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["brief_title", "summary_intro", "items", "signals"],
}

SYSTEM_INSTRUCTIONS = """You are an AI business editor creating a daily briefing.

Rules:
- Use only the facts present in the provided source material.
- Do not infer unverified numbers, partners, customers, or timelines.
- Prefer application, commercialization, adoption, enterprise workflow, go-to-market, revenue, funding, partnerships, and productization angles.
- Exclude items that are mostly about benchmarks, academic research, safety reports, or model internals unless the business impact is explicit in the evidence.
- Every output item must preserve the source_name, source_url, and published_at taken from the input.
- If the evidence is too thin, omit the item instead of guessing.
- Respond in Chinese.
- Return valid JSON only.
"""


def build_daily_brief(
    *,
    llm_config: LLMConfig,
    articles: list[Article],
    max_items: int,
    today: datetime,
) -> DailyBrief:
    if not articles:
        return fallback_brief([], today)

    candidate_limit = min(len(articles), max(6, max_items + 2))
    payload_articles = [
        {
            "title": article.title,
            "source_name": article.source_label or article.source_name,
            "source_url": article.url,
            "published_at": article.published_at.isoformat() if article.published_at else "",
            "relevance_score": round(article.score, 2),
            "score_reasons": article.score_reasons,
            "summary": article.summary[:500],
            "content_excerpt": article.content[:700],
            "fetched_excerpt": article.fetched_excerpt[:700],
        }
        for article in articles[:candidate_limit]
    ]

    user_prompt = (
        "Create a Chinese-language daily AI business briefing for one decision-maker.\n"
        f"Choose at most {max_items} items.\n"
        "Focus on why each item matters commercially or strategically.\n"
        "For each item, keep the original source link unchanged.\n"
        "Return JSON only.\n"
        "Input articles JSON:\n"
        + json.dumps(payload_articles, ensure_ascii=False, indent=2)
    )

    parsed = call_llm_for_brief(llm_config, user_prompt)
    if not parsed:
        return fallback_brief(articles[:max_items], today)

    items = normalize_brief_items(parsed.get("items", []))

    if not items:
        return fallback_brief(articles[:max_items], today)

    return DailyBrief(
        brief_title=str(parsed.get("brief_title") or f"AI 商业简报 | {today.strftime('%Y-%m-%d')}"),
        summary_intro=str(parsed.get("summary_intro") or "今日简报已根据候选资讯生成。"),
        items=items,
        signals=list(parsed.get("signals", [])),
    )


def normalize_brief_items(raw_items: object) -> list[BriefItem]:
    if not isinstance(raw_items, list):
        return []

    items: list[BriefItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue

        title = _clean_required_text(raw_item.get("title"))
        source_name = _clean_required_text(raw_item.get("source_name"))
        source_url = _clean_required_text(raw_item.get("source_url"))
        if not title or not source_name or not source_url:
            continue

        items.append(
            BriefItem(
                title=title,
                summary=_clean_optional_text(raw_item.get("summary"), "原始材料较少，建议点开原文查看。"),
                business_angle=_clean_optional_text(
                    raw_item.get("business_angle"),
                    "该消息与企业落地、产品化或商业进展相关。",
                ),
                source_name=source_name,
                source_url=source_url,
                published_at=_clean_optional_text(raw_item.get("published_at"), ""),
            )
        )
    return items


def _clean_required_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _clean_optional_text(value: object, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip() or fallback


def call_llm_for_brief(llm_config: LLMConfig, user_prompt: str) -> dict | None:
    style = llm_config.api_style.strip().lower()
    if style != "chat_completions":
        raise RuntimeError(
            f"Unsupported LLM_API_STYLE={llm_config.api_style}. Current project supports chat_completions."
        )

    body = {
        "model": llm_config.model,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }

    if llm_config.use_json_schema:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "daily_ai_business_brief",
                "strict": True,
                "schema": BRIEF_SCHEMA,
            },
        }

    payload = _post_json(
        url=f"{llm_config.base_url}/chat/completions",
        api_key=llm_config.api_key,
        body=body,
        extra_headers=llm_config.extra_headers,
        timeout_seconds=llm_config.timeout_seconds,
    )

    parsed = extract_chat_completion_json(payload)
    if parsed is not None:
        return parsed

    if llm_config.use_json_schema:
        fallback_body = {
            "model": llm_config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                {
                    "role": "user",
                    "content": user_prompt
                    + "\n\nOutput schema reminder:\n"
                    + json.dumps(BRIEF_SCHEMA, ensure_ascii=False),
                },
            ],
            "temperature": 0.2,
        }
        fallback_payload = _post_json(
            url=f"{llm_config.base_url}/chat/completions",
            api_key=llm_config.api_key,
            body=fallback_body,
            extra_headers=llm_config.extra_headers,
            timeout_seconds=llm_config.timeout_seconds,
        )
        return extract_chat_completion_json(fallback_payload)

    return None


def extract_chat_completion_json(payload: dict) -> dict | None:
    choices = payload.get("choices", [])
    if not choices:
        return None

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        return None

    text = content.strip()
    if text.startswith("```"):
        text = strip_code_fence(text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```json"):
        stripped = stripped[7:]
    elif stripped.startswith("```"):
        stripped = stripped[3:]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    return stripped.strip()


def _post_json(
    url: str,
    api_key: str,
    body: dict,
    extra_headers: dict[str, str],
    timeout_seconds: int,
) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **extra_headers,
    }
    request = Request(
        url,
        headers=headers,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"LLM API network error: {exc.reason}") from exc


def fallback_brief(articles: list[Article], today: datetime) -> DailyBrief:
    items = [
        BriefItem(
            title=article.title,
            summary=(article.summary or article.fetched_excerpt or article.content or "原始材料较少，建议点开原文查看。")[:140],
            business_angle="该消息已通过规则筛选进入简报，通常与企业落地、产品化或商业进展相关。",
            source_name=article.source_label or article.source_name,
            source_url=article.url,
            published_at=article.published_at.isoformat() if article.published_at else "",
        )
        for article in articles[:6]
    ]
    return DailyBrief(
        brief_title=f"AI 商业简报 | {today.strftime('%Y-%m-%d')}",
        summary_intro="今日简报由规则筛选生成，LLM 结构化输出暂不可用。",
        items=items,
        signals=[
            "优先关注企业落地与商业化相关消息",
            "建议继续优化信源和关键词配置",
        ],
    )
