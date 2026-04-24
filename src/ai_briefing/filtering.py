from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import re

from .models import Article, SourceConfig

POSITIVE_KEYWORDS = {
    "enterprise": 3.0,
    "business": 2.0,
    "commercial": 2.0,
    "customer": 2.5,
    "customers": 2.5,
    "customer engagement": 2.5,
    "customer service": 2.0,
    "contact center": 2.5,
    "contact centres": 2.5,
    "crm": 2.0,
    "revenue": 3.0,
    "pricing": 2.5,
    "subscription": 2.0,
    "paid": 1.5,
    "adoption": 2.5,
    "agent": 2.0,
    "agents": 2.0,
    "copilot": 2.0,
    "workflow": 2.0,
    "workflows": 2.0,
    "automation": 2.0,
    "orchestration": 2.0,
    "governance": 1.8,
    "compliance": 1.8,
    "productivity": 1.5,
    "deployment": 2.0,
    "deploy": 1.5,
    "deployed": 1.5,
    "startup": 1.5,
    "funding": 2.5,
    "valuation": 2.5,
    "acquisition": 3.0,
    "partnership": 2.0,
    "partner network": 2.0,
    "platform": 1.5,
    "end-to-end": 1.5,
    "deep context": 1.5,
    "sales": 1.5,
    "service": 1.0,
    "workspace": 1.5,
    "market": 1.5,
    "healthcare": 1.5,
    "life sciences": 1.5,
    "clinical": 1.5,
    "clinicians": 1.5,
}

NEGATIVE_KEYWORDS = {
    "benchmark": -4.0,
    "paper": -3.0,
    "research paper": -3.0,
    "system card": -4.0,
    "safety": -2.0,
    "alignment": -2.0,
    "weights": -2.0,
    "eval": -1.5,
    "dataset": -2.0,
    "open source release": -2.5,
    "open sources": -2.0,
    "tutorial": -2.0,
    "how to": -1.5,
    "keynote recap": -2.0,
    "live blog": -2.0,
    "gpu crunch": -2.5,
}


def score_articles(
    articles: list[Article],
    source_map: dict[str, SourceConfig],
    now_utc: datetime,
    lookback_hours: int,
    min_score: float,
) -> list[Article]:
    cutoff = now_utc - timedelta(hours=lookback_hours)
    scored: list[Article] = []

    for article in articles:
        if article.published_at and article.published_at < cutoff:
            continue

        source = source_map[article.source_id]
        blocked_reason = should_block_article(article, source)
        if blocked_reason:
            article.score = -999.0
            article.score_reasons = [blocked_reason]
            continue
        score, reasons = score_article(article, source, now_utc)
        article.score = score
        article.score_reasons = reasons
        if score >= min_score:
            scored.append(article)

    scored.sort(key=lambda item: (item.score, item.published_at or datetime.min.replace(tzinfo=timezone.utc)), reverse=True)
    return dedupe_articles(scored)


def score_article(article: Article, source: SourceConfig, now_utc: datetime) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = float(source.priority)
    reasons.append(f"source_priority={source.priority}")

    text = f"{article.title}\n{article.summary}\n{article.content}".lower()

    for keyword, weight in POSITIVE_KEYWORDS.items():
        if keyword in text:
            score += weight
            reasons.append(f"+{weight}:{keyword}")

    for keyword, weight in NEGATIVE_KEYWORDS.items():
        if keyword in text:
            score += weight
            reasons.append(f"{weight}:{keyword}")

    for keyword in source.include_keywords:
        if keyword.lower() in text:
            score += 1.2
            reasons.append(f"+1.2:source_include:{keyword}")

    for keyword in source.exclude_keywords:
        if keyword.lower() in text:
            score -= 2.5
            reasons.append(f"-2.5:source_exclude:{keyword}")

    if article.published_at:
        age_hours = (now_utc - article.published_at).total_seconds() / 3600
        if age_hours <= 12:
            score += 1.5
            reasons.append("+1.5:fresh")
        elif age_hours <= 24:
            score += 0.8
            reasons.append("+0.8:recent")

    if len(article.summary) < 80 and len(article.content) < 80:
        score -= 1.0
        reasons.append("-1.0:thin_feed_content")

    if re.search(r"\b(api|model|release notes|evals?)\b", text) and not re.search(
        r"\b(customer|business|enterprise|pricing|workflow|adoption|partner)\b", text
    ):
        score -= 1.5
        reasons.append("-1.5:technical_without_business_angle")

    return score, reasons


def dedupe_articles(articles: list[Article]) -> list[Article]:
    kept: list[Article] = []
    normalized_titles: list[str] = []

    for article in articles:
        normalized = normalize_title(article.title)
        duplicate = False
        for previous in normalized_titles:
            if previous == normalized:
                duplicate = True
                break
            if SequenceMatcher(None, previous, normalized).ratio() >= 0.9:
                duplicate = True
                break
        if duplicate:
            continue
        normalized_titles.append(normalized)
        kept.append(article)
    return kept


def normalize_title(title: str) -> str:
    simplified = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return " ".join(simplified.split())


def normalize_label(label: str) -> str:
    simplified = re.sub(r"[^a-z0-9]+", " ", label.lower())
    return " ".join(simplified.split())


def should_block_article(article: Article, source: SourceConfig) -> str | None:
    normalized_label = normalize_label(article.source_label or "")
    normalized_title = normalize_title(article.title)

    if source.allowed_source_labels:
        allowed = {normalize_label(label) for label in source.allowed_source_labels}
        if not normalized_label or normalized_label not in allowed:
            return "blocked:untrusted_source_label"

    if source.blocked_source_labels:
        blocked = {normalize_label(label) for label in source.blocked_source_labels}
        if normalized_label in blocked:
            return "blocked:blocked_source_label"

    for keyword in source.blocked_title_keywords:
        if normalize_title(keyword) and normalize_title(keyword) in normalized_title:
            return f"blocked:title_keyword:{keyword}"

    return None
