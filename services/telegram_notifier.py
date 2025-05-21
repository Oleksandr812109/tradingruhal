import logging
from typing import Optional, Dict, Any
import asyncio
import os

try:
    from telegram import Bot
    from telegram.error import TelegramError
    from telegram.constants import ParseMode
except ImportError as e:
    print("Telegram import error:", e)
    Bot = None
    TelegramError = Exception
    ParseMode = None

class TelegramNotifier:
    """
    Клас для асинхронного надсилання повідомлень у Telegram.
    Args:
        config (dict): Конфігурація, що містить 'token', 'chat_id'.
        logger (logging.Logger): Користувацький логер або None.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[logging.Logger] = None,
    ):
        self.logger = logger or logging.getLogger("TelegramNotifier")
        self.token = config.get("token") or os.getenv("TELEGRAM_TOKEN")
        self.chat_id = config.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID")
        self.proxy_url = config.get("proxy_url") or os.getenv("TELEGRAM_PROXY_URL")
        self._validate_config()
        self.bot = self._init_bot()

    def _validate_config(self):
        if not self.token or not isinstance(self.token, str):
            raise ValueError("Telegram token is missing or invalid.")
        if not self.chat_id or not str(self.chat_id).isdigit():
            raise ValueError("Telegram chat_id is missing or invalid (should be numeric string).")

    def _init_bot(self):
        if Bot is None:
            raise ImportError("Встановіть бібліотеку python-telegram-bot")
        if self.proxy_url:
            os.environ["HTTP_PROXY"] = self.proxy_url
            os.environ["HTTPS_PROXY"] = self.proxy_url
        return Bot(token=self.token)

    async def send_message(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
        reply_markup: Any = None,
        **kwargs
    ):
        """
        Асинхронно надсилає повідомлення у Telegram.
        """
        self.logger.debug(f"Sending async message: {text}")
        try:
            result = await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode or (ParseMode.HTML if ParseMode else None),
                disable_notification=disable_notification,
                reply_markup=reply_markup,
                **kwargs
            )
            self.logger.info("Telegram: повідомлення надіслано (async)")
            return result
        except TelegramError as e:
            self.logger.error(f"Telegram send error: {e}")
            raise
        except Exception as e:
            self.logger.exception(f"Unknown Telegram error: {e}")
            raise

    def format_message(self, template: str, params: Dict[str, Any]) -> str:
        """
        Формує повідомлення за шаблоном.
        """
        try:
            return template.format(**params)
        except Exception as e:
            self.logger.warning(f"Message formatting failed: {e}")
            return template

    def build_inline_keyboard(self, buttons: list) -> Any:
        """
        Генерує інлайн-клавіатуру.
        """
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [
                [InlineKeyboardButton(text=b["text"], callback_data=b["callback_data"]) for b in row]
                for row in buttons
            ]
            return InlineKeyboardMarkup(keyboard)
        except Exception as e:
            self.logger.warning(f"Keyboard creation failed: {e}")
            return None
