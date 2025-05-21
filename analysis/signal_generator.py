from typing import Any, Dict, List, Optional
import logging

# Додаємо імпорт sentiment-аналітика
from analysis.news_sentiment_analyzer import NewsSentimentAnalyzer

class SignalGenerator:
    def __init__(
        self, 
        models: Optional[List[Any]] = None,
        thresholds: Optional[Dict[str, Dict[str, float]]] = None,
        simple_strategy: Optional[Any] = None,
        strategy_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        news_sentiment_analyzer: Optional[NewsSentimentAnalyzer] = None
    ):
        self.models = models or []
        self.thresholds = thresholds or {"default": {"buy": 0.7, "sell": 0.3}}
        self.simple_strategy = simple_strategy
        self.strategy_id = strategy_id or "default_strategy"
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.state: Dict[str, Any] = {}
        self.news_sentiment_analyzer = news_sentiment_analyzer  # новий параметр для інтеграції

        self._validate_thresholds()

    def _validate_thresholds(self):
        for pair, th in self.thresholds.items():
            if not all(k in th for k in ("buy", "sell")):
                raise ValueError(f"Thresholds for {pair} must have keys 'buy' and 'sell'.")

    def _get_thresholds(self, symbol: str) -> Dict[str, float]:
        return self.thresholds.get(symbol, self.thresholds.get("default", {"buy": 0.7, "sell": 0.3}))

    def _ensemble_score(self, market_data):
        scores = [model.predict(market_data) for model in self.models]
        scores = [score[0] if isinstance(score, list) else score for score in scores]
        return sum(scores) / len(scores)

    def generate_signal(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        self.logger.debug(f"generate_signal called with market_data: {market_data}")

        symbol = market_data.get("symbol", "default")
        timeframe = market_data.get("timeframe")
        params_used = {}

        thresholds = self._get_thresholds(symbol)
        params_used["thresholds"] = thresholds

        if self.models:
            score = self._ensemble_score(market_data)
            params_used["model_ids"] = [getattr(m, "model_id", None) for m in self.models]
        elif self.simple_strategy:
            try:
                result = self.simple_strategy(market_data)
                score = result.get("score", 0.5)
                params_used["simple_strategy_result"] = result
            except Exception as e:
                self.logger.warning(f"Error in simple_strategy: {e}")
                score = 0.5
        else:
            score = float(market_data.get("score", 0.5))

        self.logger.debug(f"Intermediate score: {score} for symbol: {symbol}")

        action = "hold"
        if score >= thresholds["buy"]:
            action = "buy"
        elif score <= thresholds["sell"]:
            action = "sell"

        return {
            "action": action,
            "confidence": score,
            "meta": {
                "symbol": symbol,
                "params_used": params_used,
                "generated_at": market_data.get("generated_at"),
            }
        }

    # === ДОДАНО: Генерація сигналу на основі новинного сентименту ===
    def generate_signal_from_news(self, symbol: str, sentiment_score: float, meta: Optional[Dict] = None) -> dict:
        """
        Генерує сигнал на основі сентименту новин для заданого символу.
        sentiment_score: float від -1 (негативний) до 1 (позитивний)
        """
        thresholds = self._get_thresholds(symbol)
        params_used = {
            "news_sentiment_score": sentiment_score,
            "thresholds": thresholds
        }
        action = "hold"
        # Прості правила, ви можете налаштувати пороги:
        if sentiment_score >= 0.2 or (sentiment_score >= thresholds.get("buy", 0.7)):
            action = "buy"
        elif sentiment_score <= -0.2 or (sentiment_score <= thresholds.get("sell", 0.3)):
            action = "sell"

        self.logger.info(f"News-based signal for {symbol}: {action} (score={sentiment_score:.3f})")

        return {
            "action": action,
            "confidence": abs(sentiment_score),
            "meta": {
                "symbol": symbol,
                "input": "news_sentiment",
                "params_used": params_used,
                "details": meta or {},
            }
        }
