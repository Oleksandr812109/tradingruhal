import os
import logging
from typing import Any, Dict, List, Optional, Union

from binance import AsyncClient, BinanceAPIException, BinanceOrderException
from .base import (
    BaseExchange,
    ExchangeError,
    AuthenticationError,
    NetworkError,
    Order,
    OrderSide,
)

logger = logging.getLogger("binance_exchange")
logger.setLevel(logging.INFO)

class BinanceExchange(BaseExchange):
    """
    Асинхронна інтеграція з Binance Spot API.
    """

    BASE_URL = "https://api.binance.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        timeout: Optional[float] = None,
        testnet: bool = False,
    ):
        super().__init__(timeout)
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
        self.testnet = testnet
        self.client: Optional[AsyncClient] = None

    async def authenticate(self, **credentials) -> None:
        """
        Ініціалізує клієнт Binance і перевіряє ключі.
        :param credentials: Додаткові ключі, якщо потрібно.
        :raises AuthenticationError: Якщо автентифікація не вдалася.
        """
        try:
            api_key = credentials.get("api_key", self.api_key)
            api_secret = credentials.get("api_secret", self.api_secret)
            self.client = await AsyncClient.create(
                api_key, api_secret, testnet=self.testnet
            )
            # Перевірка ключів
            await self.client.get_account()
            logger.info("Binance authentication successful")
        except BinanceAPIException as e:
            logger.error(f"Authentication failed: {e}")
            raise AuthenticationError(f"Binance auth failed: {e}")
        except Exception as e:
            logger.error(f"Unknown error during authentication: {e}")
            raise NetworkError(f"Unknown error: {e}")

    async def get_price(self, symbol: str) -> float:
        """
        Отримати поточну ціну для символу (наприклад, 'BTCUSDT').
        :param symbol: Тікер пари.
        :return: Поточна ціна.
        :raises ExchangeError, NetworkError
        """
        try:
            ticker = await self.client.get_symbol_ticker(symbol=symbol)
            logger.info(f"Fetched price for {symbol}: {ticker['price']}")
            return float(ticker["price"])
        except BinanceAPIException as e:
            logger.error(f"Price fetch error: {e}")
            raise ExchangeError(f"Failed to fetch price: {e}")
        except Exception as e:
            logger.error(f"Unknown error fetching price: {e}")
            raise NetworkError(f"Unknown error: {e}")

    async def get_balance(self) -> Dict[str, float]:
        """
        Отримати баланс користувача (валюта: сума).
        :return: Словник {валюта: сума}.
        :raises ExchangeError, NetworkError
        """
        try:
            account = await self.client.get_account()
            balances = {
                asset["asset"]: float(asset["free"])
                for asset in account["balances"]
                if float(asset["free"]) > 0
            }
            logger.info(f"Fetched balances: {balances}")
            return balances
        except BinanceAPIException as e:
            logger.error(f"Balance fetch error: {e}")
            raise ExchangeError(f"Failed to fetch balance: {e}")
        except Exception as e:
            logger.error(f"Unknown error fetching balance: {e}")
            raise NetworkError(f"Unknown error: {e}")

    async def place_order(self, order: Order) -> Dict[str, Any]:
        """
        Розмістити ордер на Binance.
        Підтримує типи: market, limit, stop_limit (order.order_type).
        :param order: Order object.
        :return: Відповідь API Binance.
        :raises ExchangeError, NetworkError
        """
        try:
            # Валідація сторони
            if order.side not in [OrderSide.BUY, OrderSide.SELL]:
                raise ValueError("Invalid order side")
            params = {
                "symbol": order.symbol,
                "side": order.side.value.upper(),
                "type": order.order_type.upper(),
                "quantity": order.amount,
            }
            if order.order_type == "limit":
                params["price"] = order.price
                params["timeInForce"] = "GTC"
            if order.order_type == "stop_limit":
                params["price"] = order.price
                params["stopPrice"] = order.extra.get("stopPrice")
                params["timeInForce"] = "GTC"
            if order.extra:
                params.update(order.extra)
            resp = await self.client.create_order(**params)
            logger.info(f"Order placed: {resp}")
            return resp
        except (BinanceAPIException, BinanceOrderException) as e:
            logger.error(f"Order error: {e}")
            raise ExchangeError(f"Order failed: {e}")
        except Exception as e:
            logger.error(f"Unknown error placing order: {e}")
            raise NetworkError(f"Unknown error: {e}")

    async def get_order_status(self, order_id: Union[str, int], symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Отримати статус ордера за order_id та symbol.
        :param order_id: ID ордера.
        :param symbol: Тікер.
        :return: Інфо про ордер.
        :raises ExchangeError, NetworkError
        """
        try:
            resp = await self.client.get_order(symbol=symbol, orderId=int(order_id))
            logger.info(f"Order status fetched: {resp}")
            return resp
        except BinanceAPIException as e:
            logger.error(f"Order status error: {e}")
            raise ExchangeError(f"Order status failed: {e}")
        except Exception as e:
            logger.error(f"Unknown error fetching order status: {e}")
            raise NetworkError(f"Unknown error: {e}")

    async def cancel_order(self, order_id: Union[str, int], symbol: Optional[str] = None) -> bool:
        """
        Скасувати ордер за order_id та symbol.
        :param order_id: ID ордера.
        :param symbol: Тікер.
        :return: True, якщо успішно.
        :raises ExchangeError, NetworkError
        """
        try:
            await self.client.cancel_order(symbol=symbol, orderId=int(order_id))
            logger.info(f"Order {order_id} canceled.")
            return True
        except BinanceAPIException as e:
            if e.code == -2011:  # Order already closed
                logger.warning(f"Order {order_id} already closed: {e}")
                return True
            logger.error(f"Cancel order error: {e}")
            raise ExchangeError(f"Cancel order failed: {e}")
        except Exception as e:
            logger.error(f"Unknown error canceling order: {e}")
            raise NetworkError(f"Unknown error: {e}")

    async def get_historical_data(
        self, symbol: str, interval: str, start_time: Optional[int] = None, end_time: Optional[int] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Отримати історичні свічки для символу.
        :param symbol: Тікер.
        :param interval: '1m', '5m', '1h', '1d', etc.
        :param start_time: Початковий час (epoch ms).
        :param end_time: Кінцевий час (epoch ms).
        :param limit: Кількість свічок.
        :return: Список свічок.
        :raises ExchangeError, NetworkError
        """
        try:
            klines = await self.client.get_historical_klines(
                symbol, interval, start_str=start_time, end_str=end_time, limit=limit
            )
            candles = [
                {
                    "open_time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                    "close_time": k[6],
                }
                for k in klines
            ]
            logger.info(f"Fetched {len(candles)} candles for {symbol}")
            return candles
        except BinanceAPIException as e:
            logger.error(f"Historical data error: {e}")
            raise ExchangeError(f"Historical data failed: {e}")
        except Exception as e:
            logger.error(f"Unknown error fetching historical data: {e}")
            raise NetworkError(f"Unknown error: {e}")

    async def close(self):
        """Закрити клієнт Binance (коректно завершити сесію)"""
        if self.client:
            await self.client.close_connection()
