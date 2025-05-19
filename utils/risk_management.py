import json
import logging
from pathlib import Path
from typing import Dict, Optional, List, Any


class RiskManagerConfig:
    """
    Клас для завантаження та зберігання конфігурації RiskManager з файлу (YAML/JSON)
    """
    def __init__(self, config_path: Optional[str] = None):
        # За замовчуванням конфігурація в risk_config.json
        self.config_path = Path(config_path or "risk_config.json")
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        # Дефолтні значення
        return {
            "max_trade_size": 0.1,
            "max_daily_loss": 0.05,
            "max_weekly_loss": 0.2,
            "max_monthly_loss": 0.4,
            "max_open_positions": 5,
            "max_loss_per_position": 0.02,
            "base_currency": "USDT",
            "notify_on_limit": True,
            "commission_perc": 0.001
        }

    def save(self) -> None:
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)


class RiskManager:
    """
    Клас для управління ризиками у торгових стратегіях.

    Основні можливості:
    - Облік прибутку та збитків.
    - Ліміти для різних часових проміжків (день/тиждень/місяць).
    - Ліміти на відкриті позиції та збиток на одну позицію.
    - Динамічний розмір позиції (фіксований відсоток або власний метод).
    - Відстеження відкритих позицій (по інструменту).
    - Врахування комісій.
    - Збереження та відновлення стану.
    - Механізм сповіщення про досягнення лімітів.
    """

    def __init__(self, config: Optional[RiskManagerConfig] = None, state_path: Optional[str] = None):
        self.config = config or RiskManagerConfig()
        self.logger = logging.getLogger("RiskManager")
        # Стан
        self.daily_loss = 0.0
        self.weekly_loss = 0.0
        self.monthly_loss = 0.0
        self.profit = 0.0
        self.open_positions: Dict[str, Dict[str, Any]] = {}  # symbol -> {size, entry_price, stop_loss}
        self.state_path = Path(state_path or "risk_state.json")
        self._load_state()

    def _load_state(self):
        if self.state_path.exists():
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            self.daily_loss = state.get("daily_loss", 0.0)
            self.weekly_loss = state.get("weekly_loss", 0.0)
            self.monthly_loss = state.get("monthly_loss", 0.0)
            self.profit = state.get("profit", 0.0)
            self.open_positions = state.get("open_positions", {})
        else:
            self._save_state()

    def _save_state(self):
        state = {
            "daily_loss": self.daily_loss,
            "weekly_loss": self.weekly_loss,
            "monthly_loss": self.monthly_loss,
            "profit": self.profit,
            "open_positions": self.open_positions
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    def can_trade(self, balance: float, trade_amount: float, symbol: str, stop_loss: float) -> bool:
        """
        Перевіряє чи дозволено відкривати нову позицію.

        Аргументи:
            balance (float): поточний баланс у базовій валюті.
            trade_amount (float): розмір угоди (у базовій валюті).
            symbol (str): тикер інструменту.
            stop_loss (float): планований рівень стоп-лоссу (відносний).

        Повертає:
            bool: True якщо торгівля дозволена, False — якщо ліміти перевищені.
        """

        cfg = self.config.data

        # Кількість відкритих позицій
        if len(self.open_positions) >= cfg["max_open_positions"]:
            self.logger.warning("Досягнуто ліміт відкритих позицій.")
            return False

        # Максимальний розмір однієї угоди
        if trade_amount > balance * cfg["max_trade_size"]:
            self.logger.warning("Розмір угоди перевищує max_trade_size.")
            return False

        # Максимальний ризик на одну позицію (stop_loss)
        risk_per_pos = trade_amount * abs(stop_loss)
        if risk_per_pos > balance * cfg["max_loss_per_position"]:
            self.logger.warning("Ризик на позицію перевищує max_loss_per_position.")
            return False

        # Ліміти по збитках
        if self.daily_loss < 0 and abs(self.daily_loss) > balance * cfg["max_daily_loss"]:
            self.logger.error("Досягнуто денний ліміт збитків.")
            return False
        if self.weekly_loss < 0 and abs(self.weekly_loss) > balance * cfg["max_weekly_loss"]:
            self.logger.error("Досягнуто тижневий ліміт збитків.")
            return False
        if self.monthly_loss < 0 and abs(self.monthly_loss) > balance * cfg["max_monthly_loss"]:
            self.logger.error("Досягнуто місячний ліміт збитків.")
            return False

        return True

    def register_trade(self, symbol: str, size: float, entry_price: float, stop_loss: float):
        """
        Реєструє відкриту позицію.

        Аргументи:
            symbol (str): тикер інструменту
            size (float): розмір позиції
            entry_price (float): ціна входу
            stop_loss (float): відносний рівень стоп-лоссу (-0.01 = -1%)
        """
        self.open_positions[symbol] = {
            "size": size,
            "entry_price": entry_price,
            "stop_loss": stop_loss
        }
        self._save_state()

    def close_trade(self, symbol: str, exit_price: float, commission: Optional[float] = None):
        """
        Закриває позицію та реєструє прибуток/збиток.

        Аргументи:
            symbol (str): тикер інструменту
            exit_price (float): ціна виходу
            commission (float|None): комісія за угоду (у базовій валюті)
        """
        if symbol not in self.open_positions:
            self.logger.warning(f"Позиція {symbol} не знайдена")
            return

        pos = self.open_positions[symbol]
        pnl = (exit_price - pos["entry_price"]) * pos["size"]
        if commission is None:
            commission = abs(exit_price * pos["size"] * self.config.data.get("commission_perc", 0.0))
        pnl -= commission

        self.profit += pnl
        if pnl < 0:
            self.daily_loss += pnl
            self.weekly_loss += pnl
            self.monthly_loss += pnl

        del self.open_positions[symbol]
        self._save_state()
        self.logger.info(f"Закрито позицію {symbol}, PnL={pnl:.2f}, комісія={commission:.2f}")

        # Повідомлення про ліміт
        self._check_limits()

    def _check_limits(self):
        cfg = self.config.data
        limits = [
            ("daily_loss", cfg["max_daily_loss"]),
            ("weekly_loss", cfg["max_weekly_loss"]),
            ("monthly_loss", cfg["max_monthly_loss"])
        ]
        for loss_attr, max_loss in limits:
            loss_val = getattr(self, loss_attr)
            if loss_val < 0 and abs(loss_val) > max_loss:
                msg = f"Досягнуто/перевищено ліміт {loss_attr}: {loss_val:.2f} > {max_loss:.2f}"
                self.logger.error(msg)
                if cfg.get("notify_on_limit", True):
                    # Тут можна додати додаткове сповіщення (email, telegram тощо)
                    pass

    def reset_losses(self, interval: str = "daily"):
        """
        Скидає накопичені збитки за вказаний інтервал.

        Аргументи:
            interval (str): "daily", "weekly" або "monthly"
        """
        if interval == "daily":
            self.daily_loss = 0.0
        elif interval == "weekly":
            self.weekly_loss = 0.0
        elif interval == "monthly":
            self.monthly_loss = 0.0
        self._save_state()

    def dynamic_position_size(self, balance: float, stop_loss: float, risk_fraction: Optional[float] = None) -> float:
        """
        Динамічний розрахунок розміру позиції, виходячи з ризику на одну угоду.

        Аргументи:
            balance (float): поточний баланс
            stop_loss (float): відносний стоп-лосс (наприклад, -0.01)
            risk_fraction (float|None): частка ризику від балансу (або з config)

        Повертає:
            float: рекомендований розмір позиції
        """
        if risk_fraction is None:
            risk_fraction = self.config.data["max_loss_per_position"]
        if stop_loss == 0:
            self.logger.warning("stop_loss не може бути 0")
            return 0.0
        pos_size = balance * risk_fraction / abs(stop_loss)
        return pos_size

    def suspend_trading(self):
        """
        Тимчасово призупиняє торгівлю (можна розширити інтеграцією з ботом).
        """
        self.logger.error("Торгівлю призупинено через перевищення ризику!")

    def get_status(self) -> Dict[str, Any]:
        """
        Отримати поточний стан RiskManager.
        """
        return {
            "daily_loss": self.daily_loss,
            "weekly_loss": self.weekly_loss,
            "monthly_loss": self.monthly_loss,
            "profit": self.profit,
            "open_positions": self.open_positions
        }
