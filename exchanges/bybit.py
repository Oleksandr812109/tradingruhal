import asyncio
from typing import Any, Dict, List, Optional, Union

from .base import (
    BaseExchange,
    ExchangeError,
    AuthenticationError,
    NetworkError,
    Order,
    OrderSide,
)

class BybitMockExchange(BaseExchange):
    """
    Мок-реалізація BybitExchange для тестування без реального API.
    """

    def __init__(self, timeout: Optional[float] = None):
        super().__init__(timeout)
        self.orders = {}
        self.balances = {"USDT": 5000.0, "BTC": 2.0}
        self.next_order_id = 1

    async def authenticate(self, **credentials) -> None:
        """Імітація успішної автентифікації."""
        await asyncio.sleep(0.01)
        if credentials.get("api_key") == "invalid":
            raise AuthenticationError("Invalid API key")

    async def get_price(self, symbol: str) -> float:
        """Імітація отримання ціни."""
        await asyncio.sleep(0.01)
        prices = {"BTCUSDT": 49000, "ETHUSDT": 2950}
        if symbol not in prices:
            raise ExchangeError("Symbol not found")
        return float(prices[symbol])

    async def get_balance(self) -> Dict[str, float]:
        """Імітація отримання балансу."""
        await asyncio.sleep(0.01)
        return dict(self.balances)

    async def place_order(self, order: Order) -> Dict[str, Any]:
        """Імітація виставлення ордера."""
        await asyncio.sleep(0.01)
        order_id = str(self.next_order_id)
        self.next_order_id += 1
        self.orders[order_id] = {
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.order_type,
            "amount": order.amount,
            "status": "FILLED",
            "price": order.price or self.balances.get(order.symbol, 1.0),
            "order_id": order_id,
        }
        return self.orders[order_id]

    async def get_order_status(self, order_id: Union[str, int], symbol: Optional[str] = None) -> Dict[str, Any]:
        """Імітація отримання статусу ордера."""
        await asyncio.sleep(0.01)
        order_id = str(order_id)
        if order_id not in self.orders:
            raise ExchangeError("Order not found")
        return self.orders[order_id]

    async def cancel_order(self, order_id: Union[str, int], symbol: Optional[str] = None) -> bool:
        """Імітація скасування ордера."""
        await asyncio.sleep(0.01)
        order_id = str(order_id)
        if order_id in self.orders:
            self.orders[order_id]["status"] = "CANCELED"
            return True
        return False

    async def get_historical_data(
        self, symbol: str, interval: str, start_time: Optional[int] = None, end_time: Optional[int] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Імітація історичних даних."""
        await asyncio.sleep(0.01)
        return [
            {
                "open_time": 0,
                "open": 49000,
                "high": 49500,
                "low": 48000,
                "close": 49200,
                "volume": 12,
                "close_time": 1,
            }
            for _ in range(limit)
        ]
