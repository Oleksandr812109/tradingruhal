import asyncio
import logging

from utils.config import load_config
from analysis.signal_generator import SignalGenerator
from analysis.news_scraper import NewsScraper
from analysis.news_sentiment_analyzer import NewsSentimentAnalyzer
from services.telegram_notifier import TelegramNotifier

async def main():
    # Завантаження конфігурації
    config = load_config()
    logger = logging.getLogger("BotMain")
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    # Telegram notifier
    telegram_cfg = config.get("telegram", {})
    notifier = TelegramNotifier(telegram_cfg)

    # Символи та аліаси для аналізу (можна винести в конфіг)
    tracked_symbols = [s["name"] for s in config.get("trading", {}).get("symbols", [])]
    # Приклад аліасів для кращого знаходження згадок
    symbol_aliases = {
        "BTCUSDT": ["BTCUSDT", "BTC", "Bitcoin"],
        "ETHUSDT": ["ETHUSDT", "ETH", "Ethereum"],
        # Додайте інші символи та аліаси за потребою
    }

    # Ініціалізація news scraper та sentiment analyzer
    news_scraper = NewsScraper(
        sources=config.get("news_sources", []),
        logger=logger
    )
    news_sentiment_analyzer = NewsSentimentAnalyzer(
        symbol_aliases=symbol_aliases,
        logger=logger
    )

    # Signal generator
    signal_generator = SignalGenerator(
        thresholds=config.get("strategy", {}).get("thresholds"),
        logger=logger
    )

    # Основний цикл
    while True:
        try:
            # 1. Збір новин
            news_list = await news_scraper.fetch_news(limit=50)

            # 2. Аналіз сентименту по новинах
            sentiment_result = news_sentiment_analyzer.analyze_news(news_list, lookback_hours=3)

            # 3. Генерація і надсилання сигналів
            for symbol, sentiment_data in sentiment_result.items():
                sentiment_score = sentiment_data["sentiment"]
                if sentiment_score is None:
                    logger.info(f"Для {symbol} недостатньо згадок у новинах для аналізу.")
                    continue
                signal = signal_generator.generate_signal_from_news(
                    symbol=symbol,
                    sentiment_score=sentiment_score,
                    meta={"news_details": sentiment_data["details"]}
                )
                msg = (
                    f"Сигнал по {symbol} на основі новин: {signal['action'].upper()} "
                    f"(sentiment: {sentiment_score:.2f}, mentions: {sentiment_data['mentions']})\n"
                    f"Деталі: {signal['meta'].get('news_details', [])[:1]}"
                )
                try:
                    await notifier.send_message(msg)
                except Exception as e:
                    logger.error(f"Не вдалося надіслати сигнал у Telegram: {e}")

            # 4. (Опціонально) Генерація сигналів за ринковими даними
            # market_data_list = ... (отримуйте дані з біржі)
            # for market_data in market_data_list:
            #     signal = signal_generator.generate_signal(market_data)
            #     await notifier.send_message(...)

        except Exception as exc:
            logger.error(f"Помилка в основному циклі: {exc}")

        # Затримка між ітераціями (наприклад, 5 хвилин)
        await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())
