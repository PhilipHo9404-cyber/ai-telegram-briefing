from __future__ import annotations

import email.utils
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse, urlunparse, parse_qsl
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

from .models import Article, SourceConfig

USER_AGENT = "ai-briefing-bot/0.1 (+https://github.com/)"


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._capture_text = False
        self._chunks: list[str] = []
        self._meta_descriptions: list[str] = []
        self._current_tag = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._current_tag = tag
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if tag in {"p", "li", "h1", "h2", "h3", "article", "main", "title"}:
            self._capture_text = True
        if tag == "meta":
            name = attr_map.get("name", "").lower()
            prop = attr_map.get("property", "").lower()
            content = attr_map.get("content", "").strip()
            if content and name in {"description", "twitter:description"}:
                self._meta_descriptions.append(content)
            elif content and prop == "og:description":
                self._meta_descriptions.append(content)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "article", "main", "title"}:
            self._capture_text = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._capture_text:
            self._chunks.append(text)

    def summary_text(self, max_chars: int = 2400) -> str:
        combined = []
        seen: set[str] = set()
        for text in [*self._meta_descriptions, *self._chunks]:
            normalized = text.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            combined.append(normalized)
        result = "\n".join(combined)
        return result[:max_chars]


def fetch_all_sources(sources: Iterable[SourceConfig]) -> tuple[list[Article], list[str]]:
    articles: list[Article] = []
    errors: list[str] = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        future_map = {executor.submit(fetch_feed, source): source for source in sources}
        for future in as_completed(future_map):
            source = future_map[future]
            try:
                source_articles = future.result()
            except Exception as exc:  # pragma: no cover - defensive logging path
                errors.append(f"{source.name}: {exc}")
                continue
            articles.extend(source_articles)
    return articles, errors


def fetch_feed(source: SourceConfig) -> list[Article]:
    xml_text = _http_get_text(source.url)
    return parse_feed(xml_text, source)


def enrich_articles(articles: list[Article], max_workers: int = 4) -> None:
    targets = [article for article in articles if len(article.evidence_text()) < 700]
    if not targets:
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(fetch_page_excerpt, article.url): article for article in targets}
        for future in as_completed(future_map):
            article = future_map[future]
            try:
                article.fetched_excerpt = future.result()
            except Exception:
                article.fetched_excerpt = ""


def fetch_page_excerpt(url: str) -> str:
    html = _http_get_text(url, accept="text/html,application/xhtml+xml")
    parser = HTMLTextExtractor()
    parser.feed(html)
    return parser.summary_text()


def parse_feed(xml_text: str, source: SourceConfig) -> list[Article]:
    root = ET.fromstring(xml_text)
    tag = _local_name(root.tag)
    if tag == "rss":
        return _parse_rss(root, source)
    if tag == "feed":
        return _parse_atom(root, source)
    raise ValueError(f"Unsupported feed format: {root.tag}")


def _parse_rss(root: ET.Element, source: SourceConfig) -> list[Article]:
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[Article] = []
    for item in channel.findall("item"):
        title = _clean_html(_find_text(item, "title"))
        link = _find_text(item, "link")
        if not title or not link:
            continue
        summary = _clean_html(_find_text(item, "description"))
        content = _clean_html(_find_content_encoded(item))
        source_label = _clean_html(_find_text(item, "source"))
        published = _parse_datetime(_find_text(item, "pubDate"))
        items.append(
            Article(
                source_id=source.id,
                source_name=source.name,
                source_url=source.url,
                title=title,
                url=link.strip(),
                published_at=published,
                summary=summary,
                content=content,
                source_label=source_label or None,
                metadata={"domain": urlparse(link).netloc.lower()},
            )
        )
    return items


def _parse_atom(root: ET.Element, source: SourceConfig) -> list[Article]:
    namespace = ""
    if root.tag.startswith("{"):
        namespace = root.tag.split("}")[0] + "}"
    items: list[Article] = []
    for entry in root.findall(f"{namespace}entry"):
        title = _clean_html(_find_text(entry, f"{namespace}title"))
        link = ""
        for link_node in entry.findall(f"{namespace}link"):
            href = link_node.attrib.get("href", "").strip()
            rel = link_node.attrib.get("rel", "alternate")
            if href and rel == "alternate":
                link = href
                break
        if not link:
            continue
        summary = _clean_html(_find_text(entry, f"{namespace}summary"))
        content = _clean_html(_find_text(entry, f"{namespace}content"))
        published = _parse_datetime(
            _find_text(entry, f"{namespace}published") or _find_text(entry, f"{namespace}updated")
        )
        items.append(
            Article(
                source_id=source.id,
                source_name=source.name,
                source_url=source.url,
                title=title,
                url=link.strip(),
                published_at=published,
                summary=summary,
                content=content,
                metadata={"domain": urlparse(link).netloc.lower()},
            )
        )
    return items


def _http_get_text(url: str, accept: str = "application/rss+xml, application/atom+xml, text/xml, application/xml, text/html;q=0.9") -> str:
    normalized_url = _normalize_url(url)
    request = Request(
        normalized_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )
    context = ssl.create_default_context()
    try:
        with urlopen(request, context=context, timeout=25) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} while fetching {normalized_url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error while fetching {normalized_url}: {exc.reason}") from exc


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    path = quote(parsed.path or "/", safe="/:%-._~")
    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if query_pairs:
        query = urlencode(query_pairs, doseq=True)
    else:
        query = quote(parsed.query, safe="=&:%-._~+")

    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, query, parsed.fragment))


def _find_text(node: ET.Element, path: str) -> str:
    match = node.find(path)
    return match.text if match is not None and match.text else ""


def _find_content_encoded(node: ET.Element) -> str:
    for child in node:
        if _local_name(child.tag) == "encoded" and child.text:
            return child.text
    return ""


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _clean_html(value: str) -> str:
    if not value:
        return ""

    class _Stripper(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)

    stripper = _Stripper()
    stripper.feed(unescape(value))
    return " ".join(stripper.parts).strip()


def _parse_datetime(raw: str) -> datetime | None:
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        pass
    try:
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None
