import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from binance import AsyncClient, BinanceAPIException
from binance.enums import *
import re

@pytest.fixture(scope="module")
async def binance_client():
    """Фікстура для створення і закриття клієнта Binance."""
    client = await AsyncClient.create()
    yield client
    await client.close_connection()

@pytest.mark.asyncio
async def test_binance_ping(binance_client):
    """Тестуємо доступність Binance API через ping."""
    ping = await binance_client.ping()
    assert ping == {}, "Ping to Binance API failed: отримано не порожній словник"

@pytest.mark.asyncio
async def test_binance_time(binance_client):
    """Тестуємо, що сервер повертає коректний час і його формат."""
    server_time = await binance_client.get_server_time()
    assert "serverTime" in server_time, "Відповідь не містить ключа 'serverTime'"
    timestamp = server_time["serverTime"]
    assert isinstance(timestamp, int), f"Час має бути int, а не {type(timestamp)}"
    # Додатково перевіряємо, що це timestamp у розумних межах (не в минулому столітті)
    assert timestamp > 1500000000000, "Серверний час Binance занадто малий"

@pytest.mark.asyncio
@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT", "BNBUSDT"])
async def test_binance_symbols_contains(binance_client, symbol):
    """Тестуємо, що серед торгових пар присутній очікуваний символ."""
    exchange_info = await binance_client.get_exchange_info()
    symbols = [s["symbol"] for s in exchange_info.get("symbols", [])]
    assert symbol in symbols, f"Символ {symbol} відсутній у списку торгових пар"

@pytest.mark.asyncio
async def test_binance_symbols_structure(binance_client):
    """Тестуємо структуру першої торгової пари у відповіді API."""
    exchange_info = await binance_client.get_exchange_info()
    symbols = exchange_info.get("symbols", [])
    assert isinstance(symbols, list), "Повернене значення symbols не є списком"
    assert len(symbols) > 0, "Список торгових пар порожній"
    symbol_obj = symbols[0]
    assert "symbol" in symbol_obj, "Об'єкт торгової пари не містить ключа 'symbol'"
    assert isinstance(symbol_obj["symbol"], str), "Назва торгової пари повинна бути рядком"
    assert re.match(r"^[A-Z0-9]{6,}$", symbol_obj["symbol"]), "Назва торгової пари має невірний формат"

@pytest.mark.asyncio
async def test_binance_invalid_key():
    """Тестуємо обробку неправильного API-ключа."""
    with pytest.raises(BinanceAPIException) as exc_info:
        client = await AsyncClient.create(api_key="wrong", api_secret="wrong")
        try:
            await client.get_account()
        finally:
            await client.close_connection()
    assert "API-key format invalid" in str(exc_info.value) or "Invalid API-key" in str(exc_info.value)

@pytest.mark.asyncio
async def test_binance_invalid_symbol(binance_client):
    """Тестуємо обробку запиту до неіснуючої торгової пари."""
    with pytest.raises(BinanceAPIException) as exc_info:
        await binance_client.get_symbol_ticker(symbol="FAKESYMBOL")
    assert "Invalid symbol" in str(exc_info.value) or "invalid symbol" in str(exc_info.value)

@pytest.mark.asyncio
async def test_binance_insufficient_funds_mock():
    """Тестуємо обробку помилки недостатньо коштів через мокування API."""
    with patch("binance.AsyncClient.create_order", new_callable=AsyncMock) as mock_create_order:
        mock_create_order.side_effect = BinanceAPIException(
            {'msg': 'Account has insufficient balance for requested action.', 'code': -2010},
            status_code=400
        )
        client = await AsyncClient.create()
        try:
            with pytest.raises(BinanceAPIException) as exc_info:
                await client.create_order(
                    symbol="BTCUSDT",
                    side=SIDE_BUY,
                    type=ORDER_TYPE_MARKET,
                    quantity=1000000
                )
            assert "insufficient balance" in str(exc_info.value)
        finally:
            await client.close_connection()

@pytest.mark.asyncio
async def test_binance_rate_limit_mock():
    """Тестуємо обробку Rate Limit через мокування API."""
    with patch("binance.AsyncClient.ping", new_callable=AsyncMock) as mock_ping:
        mock_ping.side_effect = BinanceAPIException(
            {'msg': 'Too many requests. Please try again later.', 'code': -1003},
            status_code=429
        )
        client = await AsyncClient.create()
        try:
            with pytest.raises(BinanceAPIException) as exc_info:
                await client.ping()
            assert "Too many requests" in str(exc_info.value)
        finally:
            await client.close_connection()

# Якщо використовуєте WebSocket API, додайте тести нижче
@pytest.mark.asyncio
@pytest.mark.skip("Ввести реалізацію для WebSocket, якщо потрібно")
async def test_binance_websocket_connection():
    """Тестуємо підключення до WebSocket Binance (приклад, потребує доопрацювання для ваших сценаріїв)."""
    # from binance import BinanceSocketManager
    # client = await AsyncClient.create()
    # bm = BinanceSocketManager(client)
    # async with bm.symbol_ticker_socket("BTCUSDT") as stream:
    #     msg = await stream.recv()
    #     assert "s" in msg and msg["s"] == "BTCUSDT"
    # await client.close_connection()
    pass
