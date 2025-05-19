import logging
import asyncio
import aiohttp
from urllib.parse import urljoin
from typing import List, Dict, Optional, Callable, Any, Union
from bs4 import BeautifulSoup
import time
import functools

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
        """
        Args:
            sources: список словників з параметрами джерела (name, url, type, parser, selector, ...).
            logger: логер, якщо не вказано — створюється власний.
            request_delay: затримка між HTTP-запитами (секунди).
            user_agent: User-Agent для HTTP-запитів.
            cache_timeout: час життя кешу (секунд).
        """
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
        """
        Асинхронно збирає новини з усіх джерел.
        Returns:
            Список новин у вигляді словників {'title', 'url', 'source', ...}
        """
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
        """
        Асинхронно отримує новини з одного джерела (HTML/API/RSS).
        """
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
        """
        Отримує новини з HTML-сторінки (з кастомним CSS-селектором або парсером).
        """
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
        """
        Парсить новини за вказаним CSS-селектором. Витягує title, url, дату, опис (якщо можливо).
        """
        base_url = source["url"]
        articles = soup.select(selector)[:limit]
        news = []
        for art in articles:
            title = art.get_text(strip=True)
            link = art.get("href")
            if not link or not title:
                continue
            # Обробка відносних URL
            link = urljoin(base_url, link)
            news_item = {"title": title, "url": link, "source": source["name"]}
            # Додаткові поля (дата, опис)
            parent = art.parent
            desc = parent.find("p").get_text(strip=True) if parent and parent.find("p") else ""
            news_item["description"] = desc
            # Дата (можливо у data-date або в сусідніх тегах)
            date = art.get("data-date") or parent.get("data-date") if parent else None
            news_item["date"] = date
            news.append(news_item)
        return news

    async def _fetch_api(self, source: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        Отримує новини через API (очікується JSON). Можна вказати власний парсер.
        """
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
        """
        Базовий парсер для API-джерел: шукає в data['articles'].
        """
        articles = data.get("articles", [])[:limit]
        news = []
        for art in articles:
            news_item = {
                "title": art.get("title"),
                "url": art.get("url"),
                "source": source["name"],
                "description": art.get("description"),
                "date": art.get("publishedAt"),
                "author": art.get("author"),
            }
            if news_item["title"] and news_item["url"]:
                news.append(news_item)
        return news

    async def _fetch_rss(self, source: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        """
        Парсить RSS/Atom стрічки (використовує feedparser, якщо встановлено).
        """
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
                    news_item = {
                        "title": entry.get("title"),
                        "url": entry.get("link"),
                        "source": source["name"],
                        "description": entry.get("summary", ""),
                        "date": entry.get("published", ""),
                        "author": entry.get("author", ""),
                    }
                    if news_item["title"] and news_item["url"]:
                        news.append(news_item)
                return news

    def clear_cache(self):
        """Очищає кеш новин"""
        self._cache.clear()

    @staticmethod
    def example_source_html():
        """
        Приклад конфігурації джерела для HTML:
        {
            "name": "Example",
            "url": "https://example.com/news",
            "type": "html",
            "selector": "div.article a.headline",  # CSS selector
            # "parser": custom_parser_fn,  # (soup, limit, source) -> List[Dict]
        }
        """
        pass

    @staticmethod
    def example_source_api():
        """
        Приклад конфігурації джерела для API:
        {
            "name": "Some News API",
            "url": "https://api.example.com/news",
            "type": "api",
            # "parser": custom_api_parser_fn,  # (data, limit, source) -> List[Dict]
        }
        """
        pass

    @staticmethod
    def example_source_rss():
        """
        Приклад конфігурації джерела для RSS:
        {
            "name": "Some RSS",
            "url": "https://example.com/rss.xml",
            "type": "rss"
        }
        """
        pass
