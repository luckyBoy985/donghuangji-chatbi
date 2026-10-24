from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from backend.app.core.config import settings

USER_AGENT = "DonghuangjiChatBI/2.0 (internal competitive research)"


class HostRateLimiter:
    def __init__(self, delay_seconds: float, *, clock=None, sleep=None) -> None:
        self._delay = max(0.0, delay_seconds)
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._last: dict[str, float] = {}
        self._lock = Lock()

    def wait(self, url: str) -> None:
        host = urlsplit(url).netloc.lower()
        with self._lock:
            now = self._clock()
            previous = self._last.get(host)
            wait_seconds = (
                0.0
                if previous is None
                else max(0.0, previous + self._delay - now)
            )
            if wait_seconds:
                self._sleep(wait_seconds)
            self._last[host] = now + wait_seconds


def crawl_snapshot_key(
    source_id: str,
    content_hash: str,
    doc_id: str,
    extension: str,
) -> str:
    def clean(value: str) -> str:
        return re.sub(r"[^0-9A-Za-z._-]+", "_", value).strip("._") or "item"

    suffix = extension.lower().lstrip(".")
    if suffix not in {"html", "json", "txt"}:
        suffix = "txt"
    return (
        f"snapshots/{clean(source_id)}/{clean(content_hash)[:16]}/"
        f"{clean(doc_id)[:100]}.{suffix}"
    )


_crawl_rate_limiter = HostRateLimiter(settings.crawl_delay_seconds)


@dataclass(frozen=True, slots=True)
class CrawlerSpec:
    key: str
    name: str
    product: str
    official_site: str


@dataclass(slots=True)
class CrawlDocument:
    doc_id: str
    product: str
    source_type: str
    section: str
    title: str
    url: str
    published_at: str
    body: str
    content_hash: str
    raw_content: str = ""
    raw_extension: str = "txt"


CRAWLERS = {
    spec.key: spec
    for spec in (
        CrawlerSpec(
            "donghuangji",
            "东煌纪官网",
            "东煌纪",
            "https://dhj.haofangame.com",
        ),
        CrawlerSpec(
            "lqmc",
            "乐趣萌宠官网",
            "乐趣萌宠",
            "https://lqmc.net",
        ),
        CrawlerSpec(
            "pkmbattle",
            "战斗吧精灵官网",
            "战斗吧精灵",
            "https://www.pkeif.com",
        ),
        CrawlerSpec(
            "pokemon_sv",
            "宝可梦朱紫图鉴",
            "宝可梦 朱／紫",
            "https://www.pokemon.co.jp/ex/sv/sc",
        ),
    )
}

_NOISE = ("script", "style", "noscript", "svg", "iframe", "nav", "footer")
_VIEW_COUNTER = re.compile(r"\s*·?\s*\d+\s*次?(浏览|阅读|点赞|点击)")


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        }
    )
    retry = Retry(
        total=2,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def clean_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_NOISE):
        tag.decompose()
    node = (
        soup.select_one("article")
        or soup.select_one(".entry-content")
        or soup.select_one(".text-content")
        or soup.select_one("main")
        or soup.body
    )
    if node is None:
        return ""
    lines: list[str] = []
    for raw in node.get_text("\n").splitlines():
        line = _VIEW_COUNTER.sub("", raw).strip(" ·")
        if not line or (lines and lines[-1] == line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _document_from_text(
    *,
    doc_id: str,
    product: str,
    section: str,
    title: str,
    url: str,
    body: str,
    published_at: str = "",
    source_type: str = "official",
    raw_content: str = "",
    raw_extension: str = "txt",
) -> CrawlDocument:
    normalized = body.strip()
    if len(normalized) < 5:
        raise ValueError("页面未解析出足够正文")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return CrawlDocument(
        doc_id=doc_id,
        product=product,
        source_type=source_type,
        section=section,
        title=title.strip() or doc_id,
        url=url,
        published_at=published_at,
        body=normalized,
        content_hash=digest,
        raw_content=raw_content,
        raw_extension=raw_extension,
    )


def document_from_html(
    *,
    product: str,
    url: str,
    html: str,
    section: str,
    doc_id: str,
) -> CrawlDocument:
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find("h1")
    title = (
        heading.get_text(" ", strip=True)
        if heading
        else (soup.title.get_text(" ", strip=True) if soup.title else doc_id)
    )
    body_lines = clean_html_text(html).splitlines()
    if body_lines and body_lines[0].strip() == title.strip():
        body_lines = body_lines[1:]
    return _document_from_text(
        doc_id=doc_id,
        product=product,
        section=section,
        title=title,
        url=url,
        body="\n".join(body_lines),
        source_type="internal" if product == "东煌纪" else "official",
        raw_content=html,
        raw_extension="html",
    )


def _fetch(session: requests.Session, url: str) -> requests.Response:
    _crawl_rate_limiter.wait(url)
    response = session.get(url, timeout=25)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    return response


def _post_json(
    session: requests.Session,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    _crawl_rate_limiter.wait(url)
    response = session.post(
        url,
        json=payload,
        headers=headers or {},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, dict) else {}


def _crawl_donghuangji(max_pages: int) -> list[CrawlDocument]:
    spec = CRAWLERS["donghuangji"]
    base = spec.official_site
    api = "https://webaccess.qu06.cn"
    common = {"superId": 1079, "systemId": 20001, "languageType": 1001}
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json",
        "Origin": base,
        "Referer": base + "/",
    }
    session = _session()
    docs: list[CrawlDocument] = []
    records: dict[int, tuple[dict[str, Any], str]] = {}
    for content_type, label in (
        (101, "新闻"),
        (102, "活动"),
        (103, "公告"),
        (100, "最新"),
    ):
        data = _post_json(
            session,
            api + "/websiteArticle/getInformation",
            {
                **common,
                "contentType": content_type,
                "page": 1,
                "limit": min(100, max_pages * 2),
            },
            headers,
        )
        for item in data.get("data") or []:
            try:
                record_id = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            current = records.get(record_id)
            if current is None or content_type != 100:
                records[record_id] = (item, label)
    for record_id in sorted(records, reverse=True)[:max_pages]:
        item, _label = records[record_id]
        body = clean_html_text(str(item.get("content") or ""))
        published = str(item.get("startTime") or "")[:19]
        if body:
            body = f"{published[:10]}\n\n{body}".strip()
        try:
            docs.append(
                _document_from_text(
                    doc_id=f"news_{record_id}",
                    product=spec.product,
                    section="官方资讯",
                    title=str(item.get("title") or f"资讯{record_id}"),
                    url=f"{base}/newsDetails.html?pid={record_id}",
                    published_at=published,
                    body=body or "(正文为空，仅存档标题与元数据)",
                    source_type="internal",
                )
            )
        except ValueError:
            continue

    images_url = api + "/websiteActivityReservationReceive/imageList"
    for section_type, section in (
        (105, "灵兽图鉴"),
        (114, "驭灵师录"),
        (107, "巡游东煌"),
    ):
        payload = {**common, "type": section_type}
        if section_type == 107:
            payload["deviceType"] = "100"
        try:
            rows = _post_json(session, images_url, payload, headers).get("data") or []
        except Exception:
            continue
        for item in rows[:80]:
            item_id = item.get("id")
            title = str(
                item.get("animalName")
                or item.get("title")
                or item.get("jumpUrl")
                or f"{section}{item_id}"
            ).strip()
            if section == "驭灵师录":
                try:
                    people = json.loads(item.get("fieldObject") or "[]")
                except (json.JSONDecodeError, TypeError):
                    people = []
                for person in people:
                    name = str(person.get("name") or "").strip()
                    if not name:
                        continue
                    body = (
                        f"- 所属阵营: {item.get('jumpUrl') or '未知'}\n"
                        f"- 身份: {person.get('occupation') or '未知'}\n\n"
                        f"{person.get('description') or ''}"
                    )
                    docs.append(
                        _document_from_text(
                            doc_id=f"character_{_slug(name)}",
                            product=spec.product,
                            section=section,
                            title=name,
                            url=base + "/",
                            body=body,
                            source_type="internal",
                        )
                    )
                continue
            if section == "灵兽图鉴":
                attrs = [
                    attr.get("name")
                    for attr in item.get("animalAttributeList") or []
                    if isinstance(attr, dict) and attr.get("name")
                ]
                body = (
                    f"- 编号: {item.get('animalNo') or '未知'}\n"
                    f"- 属性: {'、'.join(attrs) or '未知'}\n"
                    f"- 身高: {item.get('animalHeight') or '未知'}\n"
                    f"- 体重: {item.get('animalWeight') or '未知'}\n\n"
                    f"{item.get('description') or ''}"
                )
            else:
                body = str(item.get("description") or "").strip()
            try:
                docs.append(
                    _document_from_text(
                        doc_id=f"{'hero' if section == '灵兽图鉴' else 'place'}_{item_id}",
                        product=spec.product,
                        section=section,
                        title=title,
                        url=base + "/",
                        body=body,
                        source_type="internal",
                    )
                )
            except ValueError:
                continue
    return docs[: max_pages * 3]


def _slug(value: str) -> str:
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", value).strip("_")[:60] or "item"


def _lqmc_urls(session: requests.Session) -> list[str]:
    fallback = [
        "https://lqmc.net/",
        "https://lqmc.net/pokedex.html",
        "https://lqmc.net/features.html",
        "https://lqmc.net/rewards.html",
        "https://lqmc.net/news.html",
        "https://lqmc.net/download.html",
    ]
    try:
        sitemap = _fetch(session, "https://lqmc.net/sitemap.xml").text
        locations = [
            value.strip()
            for value in re.findall(r"<loc>(.*?)</loc>", sitemap)
            if value.strip()
        ]
        urls: list[str] = []
        for location in locations:
            if not location.endswith(".xml"):
                urls.append(location)
                continue
            try:
                child = _fetch(session, location).text
            except Exception:
                continue
            urls.extend(
                value.strip()
                for value in re.findall(r"<loc>(.*?)</loc>", child)
                if value.strip() and not value.strip().endswith(".xml")
            )
        unique = [
            url
            for url in dict.fromkeys(urls)
            if "lqmc.net" in url
        ]
        return unique or fallback
    except Exception:
        return fallback


def _crawl_lqmc(max_pages: int) -> list[CrawlDocument]:
    spec = CRAWLERS["lqmc"]
    sections = {
        "": "首页",
        "pokedex.html": "萌宠图鉴",
        "features.html": "玩法特色",
        "rewards.html": "福利活动",
        "news.html": "新闻公告",
        "download.html": "下载信息",
    }
    session = _session()
    docs: list[CrawlDocument] = []
    for url in _lqmc_urls(session)[:max_pages]:
        try:
            page = _fetch(session, url)
            page_name = url.rstrip("/").rsplit("/", 1)[-1]
            section = sections.get(page_name, "官网资讯")
            docs.append(
                document_from_html(
                    product=spec.product,
                    url=url,
                    html=page.text,
                    section=section,
                    doc_id=f"lqmc_{page_name.replace('.html', '') or 'index'}",
                )
            )
        except Exception:
            continue
    return docs


def _pk_article_links(html: str) -> list[tuple[str, str, str, str]]:
    pattern = re.compile(
        r'<a\s[^>]*href="(?P<url>https://pkmbattle\.com/articleHtml/web/\d+\.html)"[^>]*>(?P<inner>.*?)</a>',
        re.S | re.I,
    )
    result: list[tuple[str, str, str, str]] = []
    seen: set[str] = set()
    for match in pattern.finditer(html):
        url = match.group("url")
        if url in seen:
            continue
        seen.add(url)
        text = re.sub(
            r"\s+",
            " ",
            re.sub(r"<[^>]+>", " ", match.group("inner")),
        ).strip()
        published = ""
        date = re.search(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?", text)
        if date:
            published = date.group(0)
            text = text.replace(published, "").strip()
        result.append((url, "资讯", text or url, published))
    return result


def _crawl_pkmbattle(max_pages: int) -> list[CrawlDocument]:
    spec = CRAWLERS["pkmbattle"]
    session = _session()
    home = _fetch(session, spec.official_site + "/")
    docs: list[CrawlDocument] = []
    for url, section, title, published in _pk_article_links(home.text)[:max_pages]:
        try:
            page = _fetch(session, url)
            body = clean_html_text(page.text)
            if len(body) < 60:
                continue
            docs.append(
                _document_from_text(
                    doc_id=(
                        "pkmb_"
                        + url.rstrip("/")
                        .rsplit("/", 1)[-1]
                        .replace(".html", "")
                    ),
                    product=spec.product,
                    section=section,
                    title=title,
                    url=url,
                    published_at=published,
                    body=body,
                )
            )
        except Exception:
            continue
    return docs


def _pokemon_detail_urls(html: str) -> list[str]:
    urls: list[str] = []
    for href in re.findall(r'href="([^"]+)"', html):
        if re.search(r"/ex/sv/sc/pokemon/[0-9]{6}_[0-9]{2}/", href):
            full = urljoin(
                "https://www.pokemon.co.jp",
                html_lib.unescape(href),
            )
            if full not in urls:
                urls.append(full)
    return urls


def _crawl_pokemon_sv(max_pages: int) -> list[CrawlDocument]:
    spec = CRAWLERS["pokemon_sv"]
    list_url = "https://www.pokemon.co.jp/ex/sv/sc/pokemon/"
    session = _session()
    listing = _fetch(session, list_url)
    docs: list[CrawlDocument] = []
    for url in _pokemon_detail_urls(listing.text)[:max_pages]:
        try:
            page = _fetch(session, url)
            docs.append(
                document_from_html(
                    product=spec.product,
                    url=url,
                    html=page.text,
                    section="官方图鉴",
                    doc_id="pksv_" + url.rstrip("/").rsplit("/", 1)[-1],
                )
            )
        except Exception:
            continue
    return docs


def crawl(crawler_key: str, max_pages: int = 60) -> list[CrawlDocument]:
    if crawler_key not in CRAWLERS:
        raise ValueError("未知数据源")
    limit = max(1, min(max_pages, 100))
    if crawler_key == "donghuangji":
        return _crawl_donghuangji(limit)
    if crawler_key == "lqmc":
        return _crawl_lqmc(limit)
    if crawler_key == "pkmbattle":
        return _crawl_pkmbattle(limit)
    if crawler_key == "pokemon_sv":
        return _crawl_pokemon_sv(limit)
    raise ValueError("未知数据源")
