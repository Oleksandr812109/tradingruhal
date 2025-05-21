import re
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union
from collections import defaultdict

# Можна підключити різні sentiment-аналітики
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
# from transformers import pipeline

class NewsSentimentAnalyzer:
    def __init__(
        self, 
        symbol_aliases: Dict[str, List[str]],
        source_weights: Optional[Dict[str, float]] = None,
        headline_weight: float = 1.5,
        recency_weight_hours: float = 3.0,  # Вік новини для ваги
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
        # self.finbert = pipeline("sentiment-analysis", model="yiyanghkust/finbert-tone") # Якщо треба FinBERT

    def extract_symbols(self, news_item: Dict[str, Any]) -> List[str]:
        text = ((news_item.get("title") or "") + " " + (news_item.get("summary") or "") + " " + (news_item.get("text") or "")).lower()
        found = set()
        for symbol, aliases in self.symbol_aliases.items():
            for alias in aliases:
                pattern = r'\b' + re.escape(alias.lower()) + r'\b'
                if re.search(pattern, text):
                    found.add(symbol)
        return list(found)

    def analyze_sentiment(self, text: str) -> float:
        """Використовуйте FinBERT або VADER."""
        # Для демонстрації: VADER
        s = self.sentiment_analyzer.polarity_scores(text)
        return s["compound"]  # [-1, 1]
        # Для FinBERT:
        # try:
        #     result = self.finbert(text)
        #     label = result[0]["label"]
        #     if label == "positive": return 1.0
        #     elif label == "negative": return -1.0
        #     else: return 0.0
        # except Exception as e:
        #     self.logger.warning(f"FinBERT failed: {e}")
        #     return 0.0

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
                published = datetime.fromisoformat(published)
            except Exception:
                return 1.0
        now = datetime.utcnow()
        hours_ago = (now - published).total_seconds() / 3600 if published else 0
        if hours_ago < self.recency_weight_hours:
            return 2.0
        elif hours_ago < self.recency_weight_hours * 2:
            return 1.2
        else:
            return 1.0

    def analyze_news(
        self, 
        news_list: List[Dict[str, Any]], 
        min_mentions: int = 1,
        lookback_hours: Optional[int] = None
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
        now = datetime.utcnow()
        scores = defaultdict(list)
        details = defaultdict(list)
        
        for news in news_list:
            # Фільтрація по часу:
            published = news.get("published") or news.get("date")
            if lookback_hours and published:
                try:
                    ts = published if isinstance(published, datetime) else datetime.fromisoformat(published)
                    if ts < now - timedelta(hours=lookback_hours):
                        continue
                except Exception:
                    self.logger.warning(f"Can't parse date: {published}")

            symbols = self.extract_symbols(news)
            if not symbols:
                continue

            headline = news.get("title", "")
            summary = news.get("summary", "")
            text = f"{headline} {summary}"
            sentiment = self.analyze_sentiment(text)
            src_weight = self.get_source_weight(news)
            for symbol in symbols:
                # headline згадка — більша вага
                is_headline = any(re.search(r'\b' + re.escape(alias.lower()) + r'\b', (headline or "").lower()) for alias in self.symbol_aliases[symbol])
                weight = src_weight * (self.headline_weight if is_headline else 1.0)
                # Вага за часом
                if published:
                    weight *= self.get_recency_weight(published)
                scores[symbol].append(sentiment * weight)
                details[symbol].append({
                    "sentiment": sentiment,
                    "source": news.get("url"),
                    "headline": headline,
                    "weight": weight,
                    "published": published,
                    "raw": news
                })
                self.logger.debug(f"Symbol: {symbol}, Sentiment: {sentiment}, Weight: {weight}, Headline: {headline[:60]}")

        result = {}
        for symbol, vals in scores.items():
            if not vals or len(vals) < min_mentions:
                result[symbol] = {
                    "sentiment": None,
                    "mentions": len(vals),
                    "details": details[symbol]
                }
            else:
                agg = sum(vals) / len(vals)
                result[symbol] = {
                    "sentiment": agg,
                    "mentions": len(vals),
                    "details": details[symbol]
                }
        return result
