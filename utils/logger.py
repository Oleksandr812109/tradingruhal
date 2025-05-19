import logging
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import List, Optional, Dict, Any, Union
import os

def get_logging_level(level: Union[int, str]) -> int:
    """
    Перетворює рядковий або числовий рівень логування у відповідну константу logging.
    """
    if isinstance(level, int):
        return level
    if isinstance(level, str):
        level = level.upper()
        if hasattr(logging, level):
            return getattr(logging, level)
    raise ValueError(f"Unknown logging level: {level}")

def setup_logger(
    name: str = "trading_bot",
    level: Union[int, str] = logging.INFO,
    handlers: Optional[List[logging.Handler]] = None,
    formatter_str: str = '[%(asctime)s] %(levelname)s: %(message)s',
    filename: Optional[str] = None,
    filemode: str = "a",
    file_encoding: Optional[str] = "utf-8",
    clean_handlers: bool = False,
    handler_levels: Optional[Dict[str, Union[int, str]]] = None,
    config_dict: Optional[Dict[str, Any]] = None,
) -> logging.Logger:
    """
    Створює та налаштовує логер з можливістю додавання кастомних обробників, форматування, ротації файлів тощо.

    Args:
        name (str): Назва логера.
        level (int|str): Базовий рівень логування для логера.
        handlers (list): Список кастомних logging.Handler.
        formatter_str (str): Формат рядка повідомлення.
        filename (str|None): Якщо передано, додає FileHandler.
        filemode (str): Режим відкриття файлу (за замовчуванням "a").
        file_encoding (str|None): Кодування для FileHandler.
        clean_handlers (bool): Якщо True — видаляє існуючі обробники логера перед додаванням нових.
        handler_levels (dict|None): Словник {handler_name: level} для індивідуальних рівнів.
        config_dict (dict|None): Якщо передано — конфігурує логування через logging.config.dictConfig.
    
    Returns:
        logging.Logger: Налаштований логер.
    """
    import logging.config

    if config_dict is not None:
        logging.config.dictConfig(config_dict)
        return logging.getLogger(name)

    logger = logging.getLogger(name)
    logger.setLevel(get_logging_level(level))
    formatter = logging.Formatter(formatter_str)

    if clean_handlers:
        logger.handlers.clear()

    # Якщо передані кастомні хендлери — додаємо їх.
    if handlers:
        for handler in handlers:
            handler.setFormatter(formatter)
            h_name = getattr(handler, "name", handler.__class__.__name__)
            # Встановлюємо рівень для конкретного handler
            if handler_levels and h_name in handler_levels:
                handler.setLevel(get_logging_level(handler_levels[h_name]))
            else:
                handler.setLevel(get_logging_level(level))
            logger.addHandler(handler)
    else:
        # Додаємо стандартний StreamHandler (консоль)
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        ch.setLevel(get_logging_level(level))
        logger.addHandler(ch)
        # Додаємо FileHandler, якщо треба
        if filename:
            try:
                fh = logging.FileHandler(filename, mode=filemode, encoding=file_encoding)
                fh.setFormatter(formatter)
                fh.setLevel(get_logging_level(level))
                logger.addHandler(fh)
            except Exception as e:
                logger.warning(f"Не вдалося створити FileHandler для {filename}: {e}")

    return logger

# Приклад використання:
# logger = setup_logger(
#     name="mybot",
#     level="DEBUG",
#     handlers=[
#         RotatingFileHandler("bot.log", maxBytes=1000000, backupCount=3),
#         TimedRotatingFileHandler("bot_timed.log", when="midnight", backupCount=7)
#     ],
#     handler_levels={"RotatingFileHandler": "INFO", "TimedRotatingFileHandler": "WARNING"},
#     clean_handlers=True
# )

# Для простих випадків:
logger = setup_logger()
