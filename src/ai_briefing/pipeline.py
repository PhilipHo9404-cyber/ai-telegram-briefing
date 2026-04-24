from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from .config import load_app_config, load_sources
from .feed_fetcher import enrich_articles, fetch_all_sources
from .filtering import score_articles
from .models import Article
from .openai_client import build_daily_brief
from .telegram import format_brief_markdown, send_telegram_message


def run_pipeline() -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = load_app_config(project_root)
    sources = load_sources(config.sources_file)
    source_map = {source.id: source for source in sources}
    now_utc = datetime.now(timezone.utc)

    raw_articles, feed_errors = fetch_all_sources(sources)
    selected = score_articles(
        raw_articles,
        source_map=source_map,
        now_utc=now_utc,
        lookback_hours=config.lookback_hours,
        min_score=config.min_relevance_score,
    )
    shortlisted = selected[: config.max_candidates]
    enrich_articles(shortlisted)

    brief = build_daily_brief(
        llm_config=config.llm,
        articles=shortlisted,
        max_items=config.max_items_in_brief,
        today=now_utc,
    )
    telegram_text = format_brief_markdown(brief)
    send_telegram_message(config.telegram_bot_token, config.telegram_chat_id, telegram_text)

    run_artifacts = {
        "generated_at": now_utc.isoformat(),
        "feed_errors": feed_errors,
        "raw_article_count": len(raw_articles),
        "selected_article_count": len(selected),
        "brief": {
            "brief_title": brief.brief_title,
            "summary_intro": brief.summary_intro,
            "signals": brief.signals,
            "items": [asdict(item) for item in brief.items],
        },
        "candidates": [serialize_article(article) for article in shortlisted],
    }

    stamp = now_utc.strftime("%Y%m%d-%H%M%S")
    artifact_path = config.output_dir / f"brief-{stamp}.json"
    artifact_path.write_text(json.dumps(run_artifacts, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Sent briefing with {len(brief.items)} items.")
    print(f"Saved run artifact to: {artifact_path}")
    if feed_errors:
        print("Feed warnings:")
        for error in feed_errors:
            print(f"- {error}")


def serialize_article(article: Article) -> dict:
    return {
        "title": article.title,
        "url": article.url,
        "source_name": article.source_name,
        "source_label": article.source_label,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "score": article.score,
        "score_reasons": article.score_reasons,
        "summary": article.summary,
        "content": article.content,
        "fetched_excerpt": article.fetched_excerpt,
        "metadata": article.metadata,
    }
