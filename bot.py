import asyncio
import logging
from analysis.news_scraper import NewsScraper
from analysis.news_sentiment_analyzer import NewsSentimentAnalyzer
from services.telegram_notifier import TelegramNotifier


# === КОНФІГУРАЦІЯ ===

SENTIMENT_THRESHOLD = 1.5
NEWS_LIMIT = 50
NEWS_INTERVAL_SECONDS = 1800  # 30 хвилин

# Приклад: додайте/змініть символи і синоніми на свої (для повної гнучкості!)
SYMBOL_ALIASES = {
    "BTCUSDT": ["BTC", "BTCUSDT", "Bitcoin"],
    "ETHUSDT": ["ETH", "ETHUSDT", "Ethereum"],
    "BNBUSDT": ["BNB", "BNBUSDT"],
    "SOLUSDT": ["SOL", "SOLUSDT", "Solana"],
    "DOGEUSDT": ["DOGE", "DOGEUSDT", "Dogecoin"],
    # Додайте більше якщо хочете
}

# Джерела новин (приклади, замініть своїми)
NEWS_SOURCES = [
    {
        "name": "Coindesk",
        "url": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "type": "rss"
    },
    {
        "name": "Binance News",
        "url": "https://www.binance.com/en/news/rss/all",
        "type": "rss"
    },
    # Додайте більше джерел за потреби
]

# Телеграм токен і чат
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"  # наприклад, -1001234567890 для групи

# === ОСНОВНИЙ ЦИКЛ ===

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logger = logging.getLogger("BotMain")

    # Ініціалізація
    news_scraper = NewsScraper(NEWS_SOURCES, logger=logger)
    sentiment_analyzer = NewsSentimentAnalyzer(SYMBOL_ALIASES, logger=logger)
    telegram = TelegramNotifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, logger=logger)

    logger.info("Бот стартував. Аналіз новин кожні 30 хвилин.")

    while True:
        try:
            news = await news_scraper.fetch_news(limit=NEWS_LIMIT)
            results = sentiment_analyzer.analyze_news(news)
            sent_count = 0
            for symbol, data in results.items():
                if data["sentiment"] >= SENTIMENT_THRESHOLD:
                    msg = (
                        f"⚡️ Сигнал по {symbol}!\n"
                        f"Sentiment: {data['sentiment']:.2f}\n"
                        f"Згадок у новинах: {data['mentions']}\n"
                        f"Остання новина: {data['details'][-1]['title'] if data['details'] else '---'}\n"
                        f"Джерело: {data['details'][-1]['url'] if data['details'] else '---'}"
                    )
                    await telegram.send_message(msg)
                    sent_count += 1
            logger.info(f"Відправлено {sent_count} сигнал(ів) у Telegram.")
        except Exception as e:
            logger.error(f"Помилка в основному циклі: {e}", exc_info=True)
        await asyncio.sleep(NEWS_INTERVAL_SECONDS)

if __name__ == "__main__":
    asyncio.run(main())
