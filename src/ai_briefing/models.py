from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SourceConfig:
    id: str
    name: str
    url: str
    priority: int = 5
    include_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    allowed_source_labels: list[str] = field(default_factory=list)
    blocked_source_labels: list[str] = field(default_factory=list)
    blocked_title_keywords: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LLMConfig:
    api_key: str
    model: str
    base_url: str
    api_style: str = "chat_completions"
    use_json_schema: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 120


@dataclass(slots=True)
class Article:
    source_id: str
    source_name: str
    source_url: str
    title: str
    url: str
    published_at: datetime | None
    summary: str = ""
    content: str = ""
    source_label: str | None = None
    score: float = 0.0
    score_reasons: list[str] = field(default_factory=list)
    fetched_excerpt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def evidence_text(self) -> str:
        parts = [self.title, self.summary, self.content, self.fetched_excerpt]
        return "\n\n".join(part.strip() for part in parts if part and part.strip())


@dataclass(slots=True)
class BriefItem:
    title: str
    summary: str
    business_angle: str
    source_name: str
    source_url: str
    published_at: str


@dataclass(slots=True)
class DailyBrief:
    brief_title: str
    summary_intro: str
    items: list[BriefItem]
    signals: list[str]
