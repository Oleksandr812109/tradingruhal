import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable, Callable, Union
from datetime import datetime
from functools import lru_cache, wraps
import asyncio

# 1. Явне визначення інтерфейсу стратегії (через Protocol)
@runtime_checkable
class StrategyProtocol(Protocol):
    id: str
    version: str

    def set_params(self, params: Dict[str, Any]) -> None:
        ...

    def generate_signal(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        ...

    async def async_generate_signal(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        ...

# 2. Схема/валідація структури сигналу
def validate_signal(signal: Dict[str, Any]) -> bool:
    """Мінімальна валідація структури сигналу."""
    required_fields = {"action", "confidence", "meta"}
    if not isinstance(signal, dict):
        return False
    if not required_fields.issubset(signal.keys()):
        return False
    return True

def signal_with_metadata(signal: Dict[str, Any], strategy: 'StrategyProtocol') -> Dict[str, Any]:
    """Додає метадані до сигналу."""
    return {
        **signal,
        "generated_at": datetime.utcnow().isoformat(),
        "strategy_id": getattr(strategy, "id", None),
        "strategy_version": getattr(strategy, "version", None),
        "signal_version": "1.0"
    }

def log_exceptions(logger):
    """Декоратор для логування виключень."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as ex:
                logger.exception(f"Exception in {func.__name__}: {ex}")
                return None
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as ex:
                logger.exception(f"Exception in {func.__name__}: {ex}")
                return None
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

class SignalService:
    """
    Сервіс для генерації, кешування, логування та обробки торгових сигналів.
    Підтримує синхронні та асинхронні стратегії, валідацію структури сигналу, метадані, агрегації та інтеграцію з зовнішніми джерелами.
    """

    def __init__(
        self,
        strategy: StrategyProtocol,
        logger: Optional[logging.Logger] = None,
        signal_cache_size: int = 128
    ):
        """
        Args:
            strategy: Об'єкт, що імплементує StrategyProtocol.
            logger: Логер (за замовчуванням створюється власний).
            signal_cache_size: Розмір кешу сигналів.
        """
        if not isinstance(strategy, StrategyProtocol):
            raise TypeError("strategy must implement StrategyProtocol")
        self.strategy = strategy
        self.logger = logger or logging.getLogger("SignalService")
        self._set_signal_cache(signal_cache_size)

    def _set_signal_cache(self, size: int):
        @lru_cache(maxsize=size)
        def _cache_signal(market_data_hash):
            # Кешується лише hashable market_data, тому передаємо hash від str(dict)
            return None
        self._cache_signal = _cache_signal

    def set_strategy_params(self, params: Dict[str, Any]) -> None:
        """Гнучке налаштування параметрів стратегії."""
        self.strategy.set_params(params)
        self.logger.info(f"Strategy parameters updated: {params}")

    @log_exceptions(logging.getLogger("SignalService"))
    def get_signal(self, market_data: Dict[str, Any], use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Генерує торговий сигнал (синхронно).
        Args:
            market_data: Дані ринку.
            use_cache: Чи використовувати кешування.
        Returns:
            Словник сигналу з метаданими, або None у разі помилки.
        """
        key = str(sorted(market_data.items()))
        if use_cache:
            cached = self._cache_signal(key)
            if cached:
                self.logger.debug("Signal fetched from cache.")
                return cached

        signal = self.strategy.generate_signal(market_data)
        if not validate_signal(signal):
            self.logger.warning(f"Invalid signal structure: {signal}")
            return None
        signal = signal_with_metadata(signal, self.strategy)
        if use_cache:
            self._cache_signal.cache_clear()  # Очищаємо кеш для актуальності
        self.logger.info(f"Signal generated: {signal}")
        return signal

    @log_exceptions(logging.getLogger("SignalService"))
    async def async_get_signal(self, market_data: Dict[str, Any], use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Генерує торговий сигнал (асинхронно).
        """
        key = str(sorted(market_data.items()))
        if use_cache:
            cached = self._cache_signal(key)
            if cached:
                self.logger.debug("Signal fetched from cache (async).")
                return cached

        signal = await self.strategy.async_generate_signal(market_data)
        if not validate_signal(signal):
            self.logger.warning(f"Invalid signal structure: {signal}")
            return None
        signal = signal_with_metadata(signal, self.strategy)
        if use_cache:
            self._cache_signal.cache_clear()
        self.logger.info(f"Async signal generated: {signal}")
        return signal

    @log_exceptions(logging.getLogger("SignalService"))
    def batch_signals(self, markets: List[Dict[str, Any]], parallel: bool = False) -> List[Optional[Dict[str, Any]]]:
        """
        Генерує сигнали для кількох ринків. Може виконувати паралельно для підвищення продуктивності.
        """
        if parallel:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                results = list(executor.map(self.get_signal, markets))
        else:
            results = [self.get_signal(m) for m in markets]
        return results

    @log_exceptions(logging.getLogger("SignalService"))
    async def async_batch_signals(self, markets: List[Dict[str, Any]], parallel: bool = False) -> List[Optional[Dict[str, Any]]]:
        """
        Асинхронно генерує сигнали для кількох ринків.
        """
        if parallel:
            results = await asyncio.gather(*(self.async_get_signal(m) for m in markets))
        else:
            results = []
            for m in markets:
                results.append(await self.async_get_signal(m))
        return results

    def filter_signals(self, signals: List[Dict[str, Any]], min_confidence: float = 0.5) -> List[Dict[str, Any]]:
        """Фільтрація сигналів за рівнем впевненості."""
        filtered = [s for s in signals if s and s.get("confidence", 0) >= min_confidence]
        self.logger.info(f"Filtered signals: {filtered}")
        return filtered

    def aggregate_signals(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Агрегує список сигналів (наприклад, визначає найпопулярніший action)."""
        from collections import Counter
        actions = [s.get("action") for s in signals if s]
        most_common = Counter(actions).most_common(1)
        agg = {"action": most_common[0][0] if most_common else None, "count": most_common[0][1] if most_common else 0}
        self.logger.info(f"Aggregated signal: {agg}")
        return agg

    # Інтеграція із зовнішніми джерелами сигналів
    def fetch_external_signal(self, fetch_fn: Callable[[], Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Отримати сигнал із зовнішнього джерела (API, webhook, файл).
        Args:
            fetch_fn: функція, яка повертає сигнал.
        """
        try:
            signal = fetch_fn()
            if not validate_signal(signal):
                self.logger.warning(f"Invalid external signal: {signal}")
                return None
            signal = signal_with_metadata(signal, self.strategy)
            self.logger.info(f"External signal fetched: {signal}")
            return signal
        except Exception as ex:
            self.logger.exception(f"Exception in fetch_external_signal: {ex}")
            return None

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Моніторинг часу виконання генерації сигналів (для продуктивності)."""
        # Для прикладу: цей метод має бути розширений у реальному використанні
        return {
            "last_signal_time": datetime.utcnow().isoformat(),
            "strategy_id": getattr(self.strategy, "id", None),
        }
