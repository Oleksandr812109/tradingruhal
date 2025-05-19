import logging
from typing import Optional, Dict, Any, Callable
import asyncio
from queue import Queue
import threading
import time
import os

try:
    from telegram import Bot
    from telegram.error import TelegramError, NetworkError, Unauthorized, BadRequest
    from telegram.constants import ParseMode
except ImportError:
    Bot = None
    TelegramError = Exception
    NetworkError = Exception
    Unauthorized = Exception
    BadRequest = Exception
    ParseMode = None

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
except ImportError:
    # Dummy decorator if tenacity is not installed
    def retry(*args, **kwargs):
        def decorator(f):
            return f
        return decorator
    RetryError = Exception

class TelegramNotifier:
    """
    Клас для асинхронного та синхронного надсилання повідомлень у Telegram із підтримкою черги, повторних спроб, форматування та проксі.

    Args:
        config (dict): Конфігурація, що містить 'token', 'chat_id', (не обов'язково) 'proxy_url'.
        logger (logging.Logger): Користувацький логер або None.
        queue_enabled (bool): Включити чергу повідомлень.
        queue_rate (float): Мінімальний інтервал між повідомленнями в черзі (секунди).
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[logging.Logger] = None,
        queue_enabled: bool = False,
        queue_rate: float = 1.0,
    ):
        self.logger = logger or logging.getLogger("TelegramNotifier")
        self.token = config.get("token") or os.getenv("TELEGRAM_TOKEN")
        self.chat_id = config.get("chat_id") or os.getenv("TELEGRAM_CHAT_ID")
        self.proxy_url = config.get("proxy_url") or os.getenv("TELEGRAM_PROXY_URL")
        self._validate_config()
        self.bot = self._init_bot()
        self.queue_enabled = queue_enabled
        self.queue_rate = queue_rate
        self._msg_queue = Queue() if self.queue_enabled else None
        self._queue_thread = None
        if self.queue_enabled:
            self._start_queue_worker()

    def _validate_config(self):
        if not self.token or not isinstance(self.token, str):
            raise ValueError("Telegram token is missing or invalid.")
        if not self.chat_id or not str(self.chat_id).isdigit():
            raise ValueError("Telegram chat_id is missing or invalid (should be numeric string).")

    def _init_bot(self):
        if Bot is None:
            raise ImportError("Встановіть бібліотеку python-telegram-bot")
        # Проксі підтримка (через request_kwargs)
        if self.proxy_url:
            from telegram.request import Request
            return Bot(token=self.token, request=Request(proxy_url=self.proxy_url))
        else:
            return Bot(token=self.token)

    def _start_queue_worker(self):
        if self._queue_thread and self._queue_thread.is_alive():
            return
        self._queue_thread = threading.Thread(target=self._queue_worker, daemon=True)
        self._queue_thread.start()
        self.logger.debug("TelegramNotifier: Queue worker started.")

    def _queue_worker(self):
        while True:
            msg_args = self._msg_queue.get()
            try:
                asyncio.run(self.send_message_async(**msg_args))
            except Exception as e:
                self.logger.exception(f"TelegramNotifier: Queue send error: {e}")
            time.sleep(self.queue_rate)
            self._msg_queue.task_done()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    def send_message(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
        reply_markup: Any = None,
        **kwargs
    ):
        """
        Синхронно надсилає повідомлення у Telegram.

        Args:
            text (str): Текст повідомлення.
            parse_mode (str): ParseMode.HTML, ParseMode.MARKDOWN, тощо.
            disable_notification (bool): Відправити без сповіщення.
            reply_markup: Інлайн-клавіатура або кнопки.
            **kwargs: Додаткові параметри для send_message.
        """
        self.logger.debug(f"Sending message: {text}")
        try:
            result = self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_notification=disable_notification,
                reply_markup=reply_markup,
                **kwargs
            )
            self.logger.info("Telegram: повідомлення надіслано (sync)")
            return result
        except (Unauthorized, BadRequest) as e:
            self.logger.error(f"Telegram error (auth/bad request): {e}")
            raise
        except NetworkError as e:
            self.logger.warning(f"Telegram network error: {e}")
            raise
        except TelegramError as e:
            self.logger.error(f"Telegram general error: {e}")
            raise
        except Exception as e:
            self.logger.exception(f"Unknown Telegram error: {e}")
            raise

    async def send_message_async(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
        reply_markup: Any = None,
        **kwargs
    ):
        """
        Асинхронно надсилає повідомлення у Telegram.

        Args:
            text (str): Текст повідомлення.
            parse_mode (str): ParseMode.HTML, ParseMode.MARKDOWN, тощо.
            disable_notification (bool): Відправити без сповіщення.
            reply_markup: Інлайн-клавіатура або кнопки.
            **kwargs: Додаткові параметри для send_message.
        """
        self.logger.debug(f"Sending async message: {text}")
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self.send_message,
                text,
                parse_mode,
                disable_notification,
                reply_markup,
                **kwargs
            )
            self.logger.info("Telegram: повідомлення надіслано (async)")
            return result
        except Exception as e:
            self.logger.exception(f"Async Telegram error: {e}")
            raise

    def queue_message(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        disable_notification: bool = False,
        reply_markup: Any = None,
        **kwargs
    ):
        """
        Додає повідомлення у чергу для надсилання із rate limit.

        Args:
            text (str): Текст повідомлення.
            parse_mode (str): Форматування.
            disable_notification (bool): Без сигналу.
            reply_markup: Кнопки.
        """
        if not self.queue_enabled:
            raise RuntimeError("Queue is not enabled for TelegramNotifier.")
        self._msg_queue.put({
            "text": text,
            "parse_mode": parse_mode,
            "disable_notification": disable_notification,
            "reply_markup": reply_markup,
            **kwargs
        })
        self.logger.debug(f"Message queued: {text}")

    def format_message(self, template: str, params: Dict[str, Any]) -> str:
        """
        Формує складне повідомлення за шаблоном.

        Args:
            template (str): Шаблон (наприклад, f-string).
            params (dict): Дані для підстановки.
        Returns:
            str: Готовий текст повідомлення.
        """
        try:
            return template.format(**params)
        except Exception as e:
            self.logger.warning(f"Message formatting failed: {e}")
            return template

    # Приклад для кнопок
    def build_inline_keyboard(self, buttons: list) -> Any:
        """
        Генерує інлайн-клавіатуру (для advanced форматування).
        Args:
            buttons (list): Список списків кнопок (text, callback_data).
        Returns:
            InlineKeyboardMarkup або None.
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

    # Метод для обробки інших типів оновлень (наприклад, edit_message_text)
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True
    )
    def edit_message(
        self,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = None,
        reply_markup: Any = None,
        **kwargs
    ):
        """
        Редагує повідомлення у Telegram за message_id.

        Args:
            message_id (int): ID повідомлення.
            text (str): Новий текст.
            parse_mode (str): Форматування.
            reply_markup: Клавіатура.
        """
        try:
            result = self.bot.edit_message_text(
                chat_id=self.chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                **kwargs
            )
            self.logger.debug(f"Message {message_id} edited.")
            return result
        except TelegramError as e:
            self.logger.error(f"Telegram edit error: {e}")
            raise
        except Exception as e:
            self.logger.exception(f"Unknown edit error: {e}")
            raise
