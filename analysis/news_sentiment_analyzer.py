import re
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Tuple, Union
from collections import defaultdict

# Можна підключити різні sentiment-аналітики
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
# from transformers import pipeline

class NewsSentimentAnalyzer:
    """
    Аналізує масив фінансових новин для формування торгових сигналів на основі сентименту.
    """

    def __init__(
        self,
        symbol_aliases: Dict[str, List[str]],
        headline_weight: float = 2.0,
        source_weights: Optional[Dict[str, float]] = None,
        recency_weight_hours: float = 6.0,
        logger: Optional[logging.Logger] = None,
    ):
        """
        symbol_aliases: { "BTCUSDT": ["BTC", "BTCUSDT", "Bitcoin"], ...}
        source_weights: {"coindesk.com": 2.0, ...}
        """
        self.symbol_aliases = symbol_aliases
        self.headline_weight = headline_weight
        self.logger = logger or logging.getLogger(__name__)
        self.source_weights = source_weights or {}
        self.recency_weight_hours = recency_weight_hours
        # baseline sentiment analyzer
        self.sentiment_analyzer = SentimentIntensityAnalyzer()

    def get_source_weight(self, news_item: Dict[str, Any]) -> float:
        url = news_item.get("url", "")
        for src, wt in self.source_weights.items():
            if src in url:
                return wt
        return 1.0

    def get_recency_weight(self, published: Union[str, datetime]) -> float:
        # Очікується, що published — datetime або ISO string
        if isinstance(published, str):
            try:
                published_dt = datetime.fromisoformat(published)
            except Exception:
                return 1.0
        else:
            published_dt = published

        # Ensure published_dt is timezone-aware (UTC)
        if published_dt.tzinfo is None:
            published_dt = published_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        hours_ago = (now - published_dt).total_seconds() / 3600 if published_dt else 0
        if hours_ago < self.recency_weight_hours:
            return 2.0
        elif hours_ago < self.recency_weight_hours * 2:
            return 1.2
        else:
            return 1.0

    def analyze_news(
        self,
        news_list: List[Dict[str, Any]],
        lookback_hours: Optional[float] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Повертає dict:
            {
                "BTCUSDT": {
                    "sentiment": 0.34,
                    "details": [ ... ],
                    "mentions": 5
                },
                ...
            }
        """
        now = datetime.now(timezone.utc)
        scores = defaultdict(list)
        details = defaultdict(list)
        
        for news in news_list:
            # Фільтрація по часу:
            published = news.get("published") or news.get("date")
            if lookback_hours and published:
                try:
                    ts = published if isinstance(published, datetime) else datetime.fromisoformat(published)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < now - timedelta(hours=lookback_hours):
                        continue
                except Exception:
                    self.logger.warning(f"Can't parse date: {published}")

            title = news.get("title", "") or ""
            description = news.get("description", "") or ""
            text = title + "\n" + description
            sentiment_score = self.sentiment_analyzer.polarity_scores(text)["compound"]

            # Для кожного символу (BTCUSDT, ETHUSDT...) рахуємо score
            for symbol, aliases in self.symbol_aliases.items():
                # Якщо символ згадується в заголовку/тексті
                if any(re.search(rf"\b{re.escape(alias)}\b", text, re.I) for alias in aliases):
                    weight = self.headline_weight if any(alias in title for alias in aliases) else 1.0
                    weight *= self.get_source_weight(news)
                    weight *= self.get_recency_weight(news.get("published") or news.get("date"))
                    scores[symbol].append(sentiment_score * weight)
                    details[symbol].append({
                        "title": title,
                        "score": sentiment_score,
                        "weight": weight,
                        "url": news.get("url"),
                        "date": str(news.get("published") or news.get("date")),
                    })

        results = {}
        for symbol in scores:
            if scores[symbol]:
                avg = sum(scores[symbol]) / len(scores[symbol])
            else:
                avg = 0
            results[symbol] = {
                "sentiment": avg,
                "details": details[symbol],
                "mentions": len(scores[symbol])
            }
        return results
