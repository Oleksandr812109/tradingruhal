import os
import json
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, Union
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

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
    return cfg.data
