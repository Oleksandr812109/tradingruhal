import os
import json
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union
from functools import lru_cache
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

# Завантажуємо змінні середовища з .env, якщо файл існує
load_dotenv()

class ConfigFileNotFound(Exception):
    """Виняток, якщо файл конфігурації не знайдено."""

class ConfigValidationError(Exception):
    """Виняток, якщо структура конфігурації некоректна."""


class AppConfigSchema(BaseModel):
    # Приклад схеми. Додайте свої поля!
    api_key: Optional[str]
    api_secret: Optional[str]
    trading:
        Optional[dict]
    logging:
        Optional[dict]

def deep_update(original: dict, overrides: dict) -> dict:
    """Рекурсивно оновлює словник original значеннями з overrides."""
    for k, v in overrides.items():
        if isinstance(v, dict) and k in original and isinstance(original[k], dict):
            original[k] = deep_update(original[k], v)
        else:
            original[k] = v
    return original


class BaseConfig:
    """Абстрактний базовий клас для конфігурації."""
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self._data = None

    def load(self) -> Dict[str, Any]:
        raise NotImplementedError

    def get(self, key: str, default=None) -> Any:
        return self.data.get(key, default)

    @property
    def data(self):
        if self._data is None:
            self._data = self.load()
        return self._data


class YamlConfig(BaseConfig):
    """Конфігурація з файлу YAML з валідацією."""
    def load(self):
        if not self.path.exists():
            print(f"Warning: Config file {self.path} not found. Using empty config.")
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"YAML error: {str(e)}")
        # Валідація та автозаповнення за схемою Pydantic
        try:
            valid_data = AppConfigSchema(**raw_data).dict()
        except ValidationError as ve:
            raise ConfigValidationError(f"Config validation error: {ve}")
        # Перезапис із середовища
        env_overrides = self._get_env_overrides()
        return deep_update(valid_data, env_overrides)
    
    def _get_env_overrides(self) -> dict:
        """Збирає всі змінні середовища, які збігаються з ключами конфіга."""
        result = {}
        for field in AppConfigSchema.__fields__:
            env_val = os.getenv(field.upper())
            if env_val is not None:
                # Пробуємо розпарсити як JSON (для складних типів)
                try:
                    env_val = json.loads(env_val)
                except Exception:
                    pass
                result[field] = env_val
        return result


class JsonConfig(BaseConfig):
    """Конфігурація з файлу JSON з валідацією."""
    def load(self):
        if not self.path.exists():
            print(f"Warning: Config file {self.path} not found. Using empty config.")
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigValidationError(f"JSON error: {str(e)}")
        try:
            valid_data = AppConfigSchema(**raw_data).dict()
        except ValidationError as ve:
            raise ConfigValidationError(f"Config validation error: {ve}")
        env_overrides = self._get_env_overrides()
        return deep_update(valid_data, env_overrides)

    def _get_env_overrides(self) -> dict:
        result = {}
        for field in AppConfigSchema.__fields__:
            env_val = os.getenv(field.upper())
            if env_val is not None:
                try:
                    env_val = json.loads(env_val)
                except Exception:
                    pass
                result[field] = env_val
        return result

class Config:
    """
    Головний клас для роботи з конфігурацією програми.
    Підтримує YAML та JSON, кешує результат, валідує структуру, підхоплює змінні середовища.
    """
    _cache = {}

    def __init__(self, path: Union[str, Path] = "config.yaml", format: Optional[str] = None):
        self.path = Path(path)
        if format:
            self.format = format.lower()
        else:
            self.format = self.path.suffix[1:].lower()
        if self.format == "yaml" or self.format == "yml":
            self.loader = YamlConfig(self.path)
        elif self.format == "json":
            self.loader = JsonConfig(self.path)
        else:
            raise ValueError(f"Unsupported config format: {self.format}")
        self._data = None

    @property
    @lru_cache()
    def data(self) -> Dict[str, Any]:
        if self._data is None:
            self._data = self.loader.data
        return self._data

    def get(self, key_chain: str, default=None) -> Any:
        """
        Дістає вкладене значення за ланцюжком ключів, наприклад: "trading.api_key"
        """
        keys = key_chain.split(".")
        d = self.data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def __getitem__(self, key):
        return self.get(key)

    def __contains__(self, key):
        return self.get(key) is not None

    def reload(self):
        """Явно перезавантажує конфігурацію з файла."""
        self._data = self.loader.load()
        self.data.cache_clear()

    def __setattr__(self, key, value):
        # Забороняємо змінювати _data після ініціалізації
        if hasattr(self, "_data") and self._data is not None and key == "_data":
            raise AttributeError("Config data is immutable after loading!")
        super().__setattr__(key, value)
