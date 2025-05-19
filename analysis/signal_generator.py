import logging
from typing import Any, Dict, List, Optional, Callable, Union, Protocol, runtime_checkable
from datetime import datetime
from enum import Enum, auto

@runtime_checkable
class ModelProtocol(Protocol):
    """
    Протокол для AI/ML моделей, що використовуються у генераторі сигналів.
    """
    model_id: str
    model_params: Dict[str, Any]

    def predict(self, market_data: Dict[str, Any]) -> float:
        ...


class SignalAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    BUY_LIMIT = "buy_limit"
    SELL_MARKET = "sell_market"
    CLOSE_POSITION = "close_position"
    # додайте інші типи сигналів за потребою


class SignalGenerator:
    """
    Клас для генерації торгових сигналів на основі ринкових даних, AI/ML моделей, або кастомних стратегій.
    Підтримує:
    - Гнучкі пороги для різних символів/стратегій
    - Комбінування кількох моделей (в ensemble-режимі)
    - Збереження стану для складних стратегій
    - Докладне логування та обробку винятків
    """

    def __init__(
        self,
        models: Optional[List[ModelProtocol]] = None,
        thresholds: Optional[Dict[str, Dict[str, float]]] = None,
        simple_strategy: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        strategy_id: Optional[str] = None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Args:
            models: список моделей, кожна з яких має метод predict(market_data) -> float
            thresholds: словник порогів для кожного символу {'BTCUSDT': {'buy': 0.7, 'sell': 0.3}, ...}
            simple_strategy: функція, що генерує сигнал при відсутності моделей
            strategy_id: ідентифікатор стратегії (для метаданих)
            logger: logger для логування
        """
        self.models = models or []
        self.thresholds = thresholds or {"default": {"buy": 0.7, "sell": 0.3}}
        self.simple_strategy = simple_strategy
        self.strategy_id = strategy_id or "default_strategy"
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.state: Dict[str, Any] = {}

        self._validate_thresholds()

    def _validate_thresholds(self):
        for pair, th in self.thresholds.items():
            if not all(k in th for k in ("buy", "sell")):
                raise ValueError(f"Thresholds for {pair} must have keys 'buy' and 'sell'.")

    def _get_thresholds(self, symbol: str) -> Dict[str, float]:
        return self.thresholds.get(symbol, self.thresholds.get("default", {"buy": 0.7, "sell": 0.3}))

    def _ensemble_score(self, market_data: Dict[str, Any]) -> float:
        scores = []
        for model in self.models:
            try:
                score = model.predict(market_data)
                self.logger.debug(f"Model {getattr(model, 'model_id', None)} predicted: {score}")
                scores.append(score)
            except Exception as e:
                self.logger.warning(f"Error in model.predict: {e}")
        if not scores:
            return 0.5
        return sum(scores) / len(scores)

    def generate_signal(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Генерує торговий сигнал на основі ринкових даних. Додає метадані, логування, обробку винятків, підтримує різні типи сигналів та стратегії.
        Args:
            market_data: Словник із ринковими даними (має містити 'symbol', 'timeframe' за можливості)
        Returns:
            signal: {'action': ..., 'confidence': ..., 'meta': ...}
        """
        self.logger.debug(f"generate_signal called with market_data: {market_data}")

        symbol = market_data.get("symbol", "default")
        timeframe = market_data.get("timeframe")
        params_used = {}

        thresholds = self._get_thresholds(symbol)
        params_used["thresholds"] = thresholds

        # Score визначається моделями або стратегією
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

        # Визначення дії
        action = SignalAction.HOLD
        if score >= thresholds["buy"]:
            action = SignalAction.BUY
        elif score <= thresholds["sell"]:
            action = SignalAction.SELL

        # Можна розширити правила для інших типів сигналів за бажанням
        # Наприклад:
        # if "close_signal" in market_data and market_data["close_signal"]:
        #     action = SignalAction.CLOSE_POSITION

        signal = {
            "action": action.value,
            "confidence": float(score),
            "generated_at": datetime.utcnow().isoformat(),
            "meta": {
                "symbol": symbol,
                "timeframe": timeframe,
                "strategy_id": self.strategy_id,
                "params_used": params_used,
                "input_market_data": market_data,
                "state_before": dict(self.state),  # копія стану перед оновленням
            }
        }

        # Оновлення стану (наприклад, для фіксації останнього сигналу)
        self.state[symbol] = {
            "last_signal": signal,
            "last_score": score,
            "last_updated": signal["generated_at"]
        }

        self.logger.info(
            f"Generated signal: action={action}, confidence={score}, symbol={symbol}, meta={signal['meta']}"
        )
        self.logger.debug(f"Signal full details: {signal}")

        return signal

    def reset_state(self) -> None:
        """
        Очищає збережений стан генератора сигналів.
        """
        self.logger.info("Resetting signal generator state.")
        self.state.clear()

    def set_thresholds(self, symbol: str, buy: float, sell: float) -> None:
        """
        Оновлює пороги для конкретного символу.
        """
        self.thresholds[symbol] = {"buy": buy, "sell": sell}
        self.logger.info(f"Thresholds for {symbol} updated: buy={buy}, sell={sell}")

    def add_model(self, model: ModelProtocol) -> None:
        """
        Додає модель до списку моделей.
        """
        self.models.append(model)
        self.logger.info(f"Model {getattr(model, 'model_id', None)} added.")

    def remove_model(self, model_id: str) -> None:
        """
        Видаляє модель за model_id.
        """
        self.models = [m for m in self.models if getattr(m, "model_id", None) != model_id]
        self.logger.info(f"Model {model_id} removed.")

    def get_state(self) -> Dict[str, Any]:
        """
        Повертає поточний стан генератора сигналів.
        """
        return dict(self.state)
