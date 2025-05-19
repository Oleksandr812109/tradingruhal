import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List, Union
from enum import Enum

# Константи для сторін ордера
class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

# Базовий клас помилок для всіх біржових взаємодій
class ExchangeError(Exception):
    """Загальна помилка взаємодії з біржею."""

class AuthenticationError(ExchangeError):
    """Помилка автентифікації на біржі."""

class NetworkError(ExchangeError):
    """Мережеві помилки/збої API."""

# Об'єкт ордера
class Order:
    def __init__(
        self,
        symbol: str,
        side: OrderSide,
        amount: float,
        price: Optional[float] = None,
        order_type: str = "market",
        extra: Optional[Dict[str, Any]] = None,
    ):
        self.symbol = symbol
        self.side = side
        self.amount = amount
        self.price = price
        self.order_type = order_type
        self.extra = extra or {}

class BaseExchange(ABC):
    """Абстрактний клас для інтеграції з біржею."""

    DEFAULT_TIMEOUT: float = 10.0  # seconds
    RETRY_ATTEMPTS: int = 3
    RETRY_DELAY: float = 1.0  # seconds

    def __init__(self, timeout: Optional[float] = None):
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    @abstractmethod
    async def authenticate(self, **credentials) -> None:
        """Автентифікація на біржі. Реалізується у дочірньому класі."""
        pass

    @abstractmethod
    async def get_price(self, symbol: str) -> float:
        """Отримати поточну ціну для символу (наприклад, 'BTCUSDT')."""
        pass

    @abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        """Отримати баланс користувача (валюта: сума)."""
        pass

    @abstractmethod
    async def place_order(self, order: Order) -> Dict[str, Any]:
        """
        Розмістити ордер.
        Повертає інформацію про створений ордер.
        """
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Отримати статус ордера за order_id."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Скасувати ордер за order_id. Повертає True, якщо вдалося."""
        pass

    @abstractmethod
    async def get_historical_data(
        self, symbol: str, interval: str, start_time: Optional[int] = None, end_time: Optional[int] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Отримати історичні дані (свічки/ціни) для символу.
        interval: наприклад '1m', '5m', '1h', '1d'
        start_time/end_time у мілісекундах (epoch ms)
        """
        pass

    async def _with_retries(self, func, *args, **kwargs):
        """Базова логіка повторних спроб для мережевих викликів."""
        for attempt in range(self.RETRY_ATTEMPTS):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=self.timeout)
            except (NetworkError, asyncio.TimeoutError) as e:
                if attempt < self.RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(self.RETRY_DELAY)
                else:
                    raise
