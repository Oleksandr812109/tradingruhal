import os
import asyncio
import logging

from utils.config import load_config
from analysis.signal_generator import SignalGenerator
from services.telegram_notifier import TelegramNotifier

# Додаткові імпорти за необхідності

def setup_logging(config):
    log_cfg = config.get('logging', {})
    filename = log_cfg.get('filename', 'logs/app.log')
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    logging.basicConfig(
        level=log_cfg.get('level', 'INFO'),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(filename),
            logging.StreamHandler()
        ]
    )

async def main():
    # Завантаження конфігурації
    config = load_config()
    setup_logging(config)
    logger = logging.getLogger("BotMain")

    # --- НОВЕ: Ініціалізація TelegramNotifier ---
    telegram_cfg = config.get("telegram", {})
    notifier = TelegramNotifier(telegram_cfg)
    # --------------------------------------------

    signal_generator = SignalGenerator(config)

    # Приклад циклу для декількох символів
    market_data_list = [
        # Тут підставте свій реальний механізм отримання даних
        {"symbol": "BTCUSDT", "timeframe": "1h"},
        {"symbol": "ETHUSDT", "timeframe": "1h"},
    ]

    state = {}

    for market_data in market_data_list:
        # Додайте реальне отримання ринкових даних тут
        # market_data = fetch_market_data(...)

        # Генерація сигналу
        signal = signal_generator.generate_signal(market_data, state_before=state)

        logger.info(f"Signal for {market_data['symbol']}: {signal}")

        # --- НОВЕ: Надсилання повідомлення в Telegram ---
        msg = (
            f"Сигнал: {signal['action'].upper()} {signal['meta']['symbol']} "
            f"(confidence: {signal['confidence']:.2f})\n"
            f"Параметри: {signal['meta'].get('params_used')}\n"
            f"Час: {signal.get('generated_at')}"
        )
        try:
            notifier.send_message(msg)
        except Exception as e:
            logger.error(f"Не вдалося надіслати сигнал у Telegram: {e}")
        # ------------------------------------------------

        # Оновлення state, якщо потрібно
        state[market_data['symbol']] = {
            "last_signal": signal,
            "last_score": signal.get("confidence", None),
            "last_updated": signal.get("generated_at"),
        }

if __name__ == "__main__":
    asyncio.run(main())
