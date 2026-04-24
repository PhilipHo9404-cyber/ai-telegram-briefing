from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .models import LLMConfig, SourceConfig


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


@dataclass(slots=True)
class AppConfig:
    llm: LLMConfig
    telegram_bot_token: str
    telegram_chat_id: str
    sources_file: Path
    output_dir: Path
    lookback_hours: int = 30
    max_candidates: int = 18
    max_items_in_brief: int = 6
    min_relevance_score: float = 5.0
    timezone: str = "Asia/Shanghai"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def load_app_config(project_root: Path) -> AppConfig:
    load_dotenv(project_root / ".env")

    output_dir = project_root / os.getenv("OUTPUT_DIR", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    sources_file = project_root / os.getenv("SOURCES_FILE", "config/sources.json")

    return AppConfig(
        llm=LLMConfig(
            api_key=_required_env("OPENAI_API_KEY"),
            model=os.getenv("OPENAI_MODEL", "").strip() or "gpt-5-mini",
            base_url=(os.getenv("LLM_BASE_URL", "").strip() or "https://api.openai.com/v1").rstrip("/"),
            api_style=(os.getenv("LLM_API_STYLE", "").strip() or "chat_completions"),
            use_json_schema=_parse_bool(os.getenv("LLM_USE_JSON_SCHEMA", "true")),
            extra_headers=_parse_json_dict(os.getenv("LLM_EXTRA_HEADERS_JSON", "")),
            timeout_seconds=max(30, int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))),
        ),
        telegram_bot_token=_required_env("TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_required_env("TELEGRAM_CHAT_ID"),
        sources_file=sources_file,
        output_dir=output_dir,
        lookback_hours=int(os.getenv("LOOKBACK_HOURS", "30")),
        max_candidates=int(os.getenv("MAX_CANDIDATES", "18")),
        max_items_in_brief=int(os.getenv("MAX_ITEMS_IN_BRIEF", "6")),
        min_relevance_score=float(os.getenv("MIN_RELEVANCE_SCORE", "5.0")),
        timezone=os.getenv("TIMEZONE", "Asia/Shanghai"),
    )


def _parse_bool(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off", ""}


def _parse_json_dict(value: str) -> dict[str, str]:
    raw = value.strip()
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("LLM_EXTRA_HEADERS_JSON must be a JSON object")
    return {str(key): str(val) for key, val in parsed.items()}


def load_sources(path: Path) -> list[SourceConfig]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        SourceConfig(
            id=item["id"],
            name=item["name"],
            url=item["url"],
            priority=int(item.get("priority", 5)),
            include_keywords=list(item.get("include_keywords", [])),
            exclude_keywords=list(item.get("exclude_keywords", [])),
            allowed_source_labels=list(item.get("allowed_source_labels", [])),
            blocked_source_labels=list(item.get("blocked_source_labels", [])),
            blocked_title_keywords=list(item.get("blocked_title_keywords", [])),
        )
        for item in payload
    ]
