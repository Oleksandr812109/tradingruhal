import os
import json
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union, List
from functools import lru_cache
from dotenv import load_dotenv
import re

load_dotenv()

def interpolate_env_vars(obj):
    if isinstance(obj, dict):
        return {k: interpolate_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [interpolate_env_vars(i) for i in obj]
    elif isinstance(obj, str):
        pattern = re.compile(r'\$\{([^}^{]+)\}')
        match = pattern.findall(obj)
        for g in match:
            obj = obj.replace(f'${{{g}}}', os.environ.get(g, f'${{{g}}}'))
        return obj
    else:
        return obj

class ConfigFileNotFound(Exception):
    pass

class ConfigValidationError(Exception):
    pass

def deep_update(original: dict, overrides: dict) -> dict:
    for k, v in overrides.items():
        if isinstance(v, dict) and k in original and isinstance(original[k], dict):
            original[k] = deep_update(original[k], v)
        else:
            original[k] = v
    return original

class BaseConfig:
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
    """Конфігурація з файлу YAML без суворої валідації."""
    def load(self):
        if not self.path.exists():
            print(f"Warning: Config file {self.path} not found. Using empty config.")
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw_data = yaml.safe_load(f) or {}
                raw_data = interpolate_env_vars(raw_data)  # Підстановка змінних оточення!
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"YAML error: {str(e)}")
        return raw_data

class Config:
    def __init__(self, path: Union[str, Path] = "config.yaml", format: Optional[str] = None):
        self.path = Path(path)
        if format:
            self.format = format.lower()
        else:
            self.format = self.path.suffix[1:].lower()
        if self.format == "yaml" or self.format == "yml":
            self.loader = YamlConfig(self.path)
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
        self._data = self.loader.load()
        self.data.cache_clear()

    def __setattr__(self, key, value):
        if hasattr(self, "_data") and self._data is not None and key == "_data":
            raise AttributeError("Config data is immutable after loading!")
        super().__setattr__(key, value)

def load_config(config_path: str = "config.yaml", env: str = None):
    cfg = Config(config_path)
    # Витягуємо потрібне середовище
    data = cfg.data
    environments = data.get("environments", {})
    # Визначаємо, яке середовище використовувати
    env_name = env or os.environ.get("ENVIRONMENT", "default")
    env_config = environments.get(env_name, environments.get("default", {}))
    # Для простоти підвантажуємо news_sources саме з цього середовища (default, production, test)
    data_flat = {}
    data_flat.update(env_config)
    return data_flat

def get_news_sources(config_path: str = "config.yaml", env: str = None) -> List[Dict[str, Any]]:
    """
    Повертає список джерел новин з відповідного середовища в config.yaml
    """
    config = load_config(config_path, env)
    return config.get("news_sources", [])
