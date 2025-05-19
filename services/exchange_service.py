from typing import Any, Dict, Optional, Callable, List, Union
from decimal import Decimal, getcontext

getcontext().prec = 10  # Встановлюємо точність для Decimal

class ExchangeService:
    """
    Сервіс для взаємодії з біржею та управління ризиками для трейдингу.
    """

    def __init__(
        self,
        exchange,
        risk_config: Optional[Dict[str, Any]] = None,
        risk_limits: Optional[Dict[str, Any]] = None,
        risk_event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ):
        """
        Args:
            exchange: Біржовий API-адаптер (наприклад, ccxt або кастомний клас).
            risk_config: Загальні налаштування ризику (max_trade_size, max_daily_loss тощо).
            risk_limits: Специфічні ліміти для інструментів (наприклад, {'BTCUSDT': {'max_trade_size': 0.05}})
            risk_event_callback: Функція для виклику при досягненні лімітів.
        """
        self.exchange = exchange
        self.risk_config = risk_config or {
            "max_trade_size_pct": Decimal("0.1"),
            "max_trade_size_abs": Decimal("10000"),
            "max_daily_loss_pct": Decimal("0.05"),
            "max_daily_loss_abs": Decimal("500"),
            "max_open_trades": 5
        }
        self.risk_limits = risk_limits or {}
        self.risk_event_callback = risk_event_callback
        self.open_trades: List[Dict[str, Any]] = []
        self.daily_loss = Decimal("0")
        self.trade_log: List[Dict[str, Any]] = []

    def _get_pair_limits(self, symbol: str) -> Dict[str, Any]:
        """Повертає ліміти ризику для конкретного торгового інструменту."""
        return self.risk_limits.get(symbol, self.risk_config)

    def _total_open_risk(self, symbol: Optional[str] = None) -> Decimal:
        """Підраховує поточний сумарний ризик у відкритих позиціях (можна фільтрувати по символу)."""
        return sum(
            Decimal(str(trade["amount"]))
            for trade in self.open_trades
            if symbol is None or trade["symbol"] == symbol
        )

    def can_trade(
        self,
        balance: Union[float, Decimal],
        trade_amount: Union[float, Decimal],
        symbol: str
    ) -> bool:
        """
        Перевіряє, чи дозволено відкривати нову позицію згідно з ризик-менеджментом.
        """
        balance = Decimal(str(balance))
        trade_amount = Decimal(str(trade_amount))
        limits = self._get_pair_limits(symbol)
        total_open = self._total_open_risk(symbol)
        max_trade_size_pct = Decimal(str(limits.get("max_trade_size_pct", "0.1")))
        max_trade_size_abs = Decimal(str(limits.get("max_trade_size_abs", "10000")))
        max_open_trades = limits.get("max_open_trades", self.risk_config["max_open_trades"])

        # Перевірка максимальної кількості відкритих угод
        if len(self.open_trades) >= max_open_trades:
            self._notify_risk("max_open_trades", {"open_trades": len(self.open_trades)})
            return False

        # Перевірка сумарного ризику по символу (сума вже відкритих + нова угода)
        if total_open + trade_amount > balance * max_trade_size_pct:
            self._notify_risk("sum_trade_size_pct", {"total_open": str(total_open), "try_add": str(trade_amount)})
            return False

        # Абсолютний ліміт (сума відкритих + нова угода)
        if total_open + trade_amount > max_trade_size_abs:
            self._notify_risk("sum_trade_size_abs", {"total_open": str(total_open), "try_add": str(trade_amount)})
            return False

        # Перевірка, чи вистачає балансу
        if trade_amount > balance:
            self._notify_risk("insufficient_balance", {"balance": str(balance), "trade_amount": str(trade_amount)})
            return False

        return True

    def create_order(
        self,
        symbol: str,
        side: str,
        amount: Union[float, Decimal],
        price: Optional[Union[float, Decimal]] = None,
        order_type: str = "market"
    ) -> Dict[str, Any]:
        """
        Створює ордер, якщо це дозволяє ризик-менеджмент.
        """
        balance = self.get_balance().get("free", 0)
        if not self.can_trade(balance, amount, symbol):
            raise Exception("Risk limits exceeded or insufficient funds")
        order = self.exchange.create_order(symbol, side, float(amount), float(price) if price else None, order_type)
        self.open_trades.append({
            "symbol": symbol,
            "side": side,
            "amount": str(amount),
            "price": str(price) if price else None,
            "order_type": order_type,
            "order_id": order.get("id")
        })
        self.trade_log.append({"event": "order_created", "order": order})
        return order

    def close_order(self, order_id: str, symbol: str, pnl: Union[float, Decimal], loss: bool = False, meta: Optional[Dict] = None):
        """
        Закриває ордер і реєструє прибуток/збиток.
        """
        self.open_trades = [t for t in self.open_trades if t.get("order_id") != order_id]
        if loss:
            self.register_loss(symbol, pnl, meta)
        else:
            self.register_profit(symbol, pnl, meta)
        self.trade_log.append({"event": "order_closed", "id": order_id, "symbol": symbol, "pnl": pnl, "loss": loss})

    def register_loss(self, symbol: str, loss: Union[float, Decimal], meta: Optional[Dict] = None):
        """Реєструє збиток, враховуючи абсолютні та відсоткові ліміти."""
        loss = Decimal(str(loss))
        self.daily_loss += loss
        if meta is None:
            meta = {}
        meta.update({"symbol": symbol, "loss": str(loss)})
        # Абсолютний та відсотковий ліміт
        if abs(self.daily_loss) > self.risk_config["max_daily_loss_abs"]:
            self._notify_risk("max_daily_loss_abs", {"daily_loss": str(self.daily_loss)})
        if abs(self.daily_loss) > self.risk_config["max_daily_loss_pct"]:
            self._notify_risk("max_daily_loss_pct", {"daily_loss": str(self.daily_loss)})

    def register_profit(self, symbol: str, profit: Union[float, Decimal], meta: Optional[Dict] = None):
        """Реєструє прибуток (можна розширити для аналітики)."""
        if meta is None:
            meta = {}
        meta.update({"symbol": symbol, "profit": str(profit)})

    def get_balance(self) -> Dict[str, Any]:
        """Отримати баланс (основна валюта)."""
        bal = self.exchange.get_balance()
        # Для точності — перетворюємо на Decimal
        if "free" in bal:
            bal["free"] = Decimal(str(bal["free"]))
        return bal

    def get_risk_state(self) -> Dict[str, Any]:
        """
        Повертає поточний стан ризику:
        - daily_loss (abs/percent)
        - кількість відкритих угод
        - сумарний розмір відкритих позицій
        """
        balance = self.get_balance().get("free", Decimal("0"))
        daily_loss_pct = (self.daily_loss / balance * 100) if balance else Decimal("0")
        return {
            "daily_loss_abs": str(self.daily_loss),
            "daily_loss_pct": str(daily_loss_pct),
            "open_trades_count": len(self.open_trades),
            "open_trades_total_amount": str(self._total_open_risk()),
        }

    def update_limits(self, new_limits: Dict[str, Any], symbol: Optional[str] = None):
        """Тимчасово оновлює ліміти ризику (глобально або для конкретного символу)."""
        if symbol:
            self.risk_limits[symbol] = new_limits
        else:
            self.risk_config.update(new_limits)

    def _notify_risk(self, event: str, details: Dict[str, Any]):
        """Викликає колбек при досягненні ліміту ризику."""
        if self.risk_event_callback:
            self.risk_event_callback(event, details)

    # Приклад: ви можете розширити цей клас методами для інтеграції зі своїм RiskManager,
    # деталізованими стратегіями виходу, різними валютами тощо.
