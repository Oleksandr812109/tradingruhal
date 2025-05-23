import logging
import asyncio
import aiohttp
from urllib.parse import urljoin
from typing import List, Dict, Optional, Callable, Any, Union
from bs4 import BeautifulSoup
import time
import functools
from dateutil import parser as dateparser  # Додаємо універсальний парсер дат

class NewsScraper:
    """
    Клас для збору фінансових новин з різних джерел (HTML, API, RSS/Atom).
    Підтримує асинхронний збір, кастомні парсери для кожного джерела, кешування, обробку кодувань, User-Agent, логування та додаткову інформацію (дата, опис тощо).
    """

    def __init__(
        self,
        sources: List[Dict[str, Any]],
        logger: Optional[logging.Logger] = None,
        request_delay: float = 0.5,
        user_agent: str = "Mozilla/5.0 (compatible; NewsScraperBot/1.0)",
        cache_timeout: int = 300,
    ):
        self.sources = sources
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.request_delay = request_delay
        self.user_agent = user_agent
        self.cache_timeout = cache_timeout
        self._cache: Dict[str, Any] = {}  # {cache_key: (timestamp, data)}
        self._validate_sources()

    def _validate_sources(self):
        for source in self.sources:
            if not all(k in source for k in ("name", "url", "type")):
                raise ValueError(f"Source {source} must have 'name', 'url' and 'type' keys")
            if source["type"] not in ("html", "api", "rss"):
                raise ValueError(f"Unknown source type for {source['name']}: {source['type']}")

    async def fetch_news(self, limit: int = 10) -> List[Dict[str, Any]]:
        cache_key = f"news_{limit}"
        now = time.time()
        if cache_key in self._cache:
            ts, data = self._cache[cache_key]
            if now - ts < self.cache_timeout:
                self.logger.debug("Returning news from cache")
                return data.copy()

        tasks = [self._fetch_from_source(source, limit) for source in self.sources]
        all_news: List[Dict[str, Any]] = []
        for coro in asyncio.as_completed(tasks):
            try:
                news = await coro
                all_news.extend(news)
            except Exception as e:
                self.logger.warning(f"Failed to fetch from source: {e}")
        all_news = all_news[:limit]
        self._cache[cache_key] = (now, all_news)
        self.logger.info(f"Fetched {len(all_news)} news items in total")
        return all_news

    async def _fetch_from_source(self, source: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        await asyncio.sleep(self.request_delay)  # Не перевантажуємо сервери
        typ = source["type"]
        if typ == "html":
            return await self._fetch_html(source, limit)
        elif typ == "api":
            return await self._fetch_api(source, limit)
        elif typ == "rss":
            return await self._fetch_rss(source, limit)
        else:
            self.logger.error(f"Unknown source type: {typ}")
            return []

    async def _fetch_html(self, source: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        url = source["url"]
        selector = source.get("selector", "a")
        parser_fn: Optional[Callable[[BeautifulSoup, int, Dict[str, Any]], List[Dict[str, Any]]]] = source.get("parser")
        headers = {"User-Agent": self.user_agent}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    self.logger.warning(f"HTTP error {resp.status} for {url}")
                    return []
                encoding = resp.charset or "utf-8"
                text = await resp.text(encoding=encoding)
                soup = BeautifulSoup(text, "html.parser")
                if parser_fn:
                    news = parser_fn(soup, limit, source)
                else:
                    news = self._default_html_parser(soup, limit, source, selector)
        self.logger.info(f"Fetched {len(news)} news from {source['name']}")
        return news

    def _default_html_parser(
        self, soup: BeautifulSoup, limit: int, source: Dict[str, Any], selector: str
    ) -> List[Dict[str, Any]]:
        base_url = source["url"]
        articles = soup.select(selector)[:limit]
        news = []
        for art in articles:
            title = art.get_text(strip=True)
            link = art.get("href")
            if not link or not title:
                continue
            link = urljoin(base_url, link)
            news_item = {"title": title, "url": link, "source": source["name"]}
            parent = art.parent
            desc = parent.find("p").get_text(strip=True) if parent and parent.find("p") else ""
            news_item["description"] = desc
            date = art.get("data-date") or parent.get("data-date") if parent else None
            # Парсинг дати через dateutil
            if date:
                try:
                    parsed_date = dateparser.parse(date)
                    news_item["date"] = parsed_date.isoformat() if parsed_date else date
                except Exception:
                    self.logger.warning(f"Can't parse date: {date}")
                    news_item["date"] = date
            else:
                news_item["date"] = None
            news.append(news_item)
        return news

    async def _fetch_api(self, source: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        url = source["url"]
        parser_fn: Optional[Callable[[Any, int, Dict[str, Any]], List[Dict[str, Any]]]] = source.get("parser")
        headers = {"User-Agent": self.user_agent}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    self.logger.warning(f"API HTTP error {resp.status} for {url}")
                    return []
                data = await resp.json()
                if parser_fn:
                    news = parser_fn(data, limit, source)
                else:
                    news = self._default_api_parser(data, limit, source)
        self.logger.info(f"Fetched {len(news)} news from API {source['name']}")
        return news

    def _default_api_parser(self, data: Any, limit: int, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        articles = data.get("articles", [])[:limit]
        news = []
        for art in articles:
            news_item = {
                "title": art.get("title"),
                "url": art.get("url"),
                "source": source["name"],
                "description": art.get("description"),
                "author": art.get("author"),
            }
            date = art.get("publishedAt")
            if date:
                try:
                    parsed_date = dateparser.parse(date)
                    news_item["date"] = parsed_date.isoformat() if parsed_date else date
                except Exception:
                    self.logger.warning(f"Can't parse date: {date}")
                    news_item["date"] = date
            else:
                news_item["date"] = None
            if news_item["title"] and news_item["url"]:
                news.append(news_item)
        return news

    async def _fetch_rss(self, source: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        try:
            import feedparser
        except ImportError:
            self.logger.error("feedparser is required for RSS/Atom support")
            return []
        url = source["url"]
        headers = {"User-Agent": self.user_agent}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    self.logger.warning(f"RSS HTTP error {resp.status} for {url}")
                    return []
                text = await resp.text()
                feed = feedparser.parse(text)
                entries = feed.entries[:limit]
                news = []
                for entry in entries:
                    date = entry.get("published", "") or ""
                    news_item = {
                        "title": entry.get("title"),
                        "url": entry.get("link"),
                        "source": source["name"],
                        "description": entry.get("summary", ""),
                        "author": entry.get("author", ""),
                    }
                    # Парсинг дати через dateutil
                    if date:
                        try:
                            parsed_date = dateparser.parse(date)
                            news_item["date"] = parsed_date.isoformat() if parsed_date else date
                        except Exception:
                            self.logger.warning(f"Can't parse date: {date}")
                            news_item["date"] = date
                    else:
                        news_item["date"] = None
                    if news_item["title"] and news_item["url"]:
                        news.append(news_item)
                return news

    def clear_cache(self):
        self._cache.clear()

    @staticmethod
    def example_source_html():
        pass

    @staticmethod
    def example_source_api():
        pass

    @staticmethod
    def example_source_rss():
        pass
