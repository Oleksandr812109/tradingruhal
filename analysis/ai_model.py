import logging
from typing import Any, Dict, Optional, Callable, List, Union
from abc import ABC, abstractmethod

try:
    import numpy as np
    import pandas as pd
except ImportError:
    np = None
    pd = None

class AIModelBase(ABC):
    """
    Абстрактний базовий клас для AI/ML моделей у трейдинг-системі.
    
    Підтримує:
    - Гнучке керування гіперпараметрами
    - Логування
    - Контроль версії моделі
    - Базові методи для навчання, прогнозування, оцінки, збереження/завантаження
    - Підтримку колбеків
    - Перевірку на навченість
    """

    model_version: str = "1.0"

    def __init__(
        self,
        model_params: Optional[Dict[str, Any]] = None,
        callbacks: Optional[List[Callable]] = None
    ):
        """
        Args:
            model_params: Гіперпараметри моделі
            callbacks: Список колбеків, що викликаються під час навчання
        """
        self.model_params = model_params or {}
        self.callbacks = callbacks or []
        self.logger = logging.getLogger(self.__class__.__name__)
        self.model = None
        self.is_trained = False
        self.metadata: Dict[str, Any] = {"version": self.model_version}

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Назва моделі"""
        pass

    @abstractmethod
    def train(
        self,
        X: Union["np.ndarray", "pd.DataFrame"],
        y: Union["np.ndarray", "pd.Series", List[Any]]
    ) -> None:
        """
        Навчання моделі на даних.
        Args:
            X: Матриця ознак (features)
            y: Вектор міток (labels)
        Raises:
            Exception: У разі помилки навчання
        """
        pass

    @abstractmethod
    def predict(
        self,
        X: Union["np.ndarray", "pd.DataFrame"]
    ) -> Union["np.ndarray", List[float]]:
        """
        Прогнозування на основі нових даних.
        Args:
            X: Матриця ознак
        Returns:
            np.ndarray або список прогнозів
        Raises:
            Exception: Якщо модель не навчена або при помилці прогнозування
        """
        pass

    @abstractmethod
    def evaluate(
        self,
        X_test: Union["np.ndarray", "pd.DataFrame"],
        y_test: Union["np.ndarray", "pd.Series", List[Any]]
    ) -> Dict[str, float]:
        """
        Оцінка якості моделі на тестових даних.
        Args:
            X_test: Тестові ознаки
            y_test: Тестові мітки
        Returns:
            Словник з метриками якості (accuracy, precision тощо)
        """
        pass

    def preprocess_data(
        self,
        data: Union["pd.DataFrame", Any]
    ) -> Union["pd.DataFrame", Any]:
        """
        Попередня обробка даних. Може бути перевизначено у підкласі.
        Args:
            data: Вхідні дані
        Returns:
            Оброблені дані
        """
        self.logger.debug("Preprocessing data...")
        return data

    def set_params(self, params: Dict[str, Any]) -> None:
        """
        Встановлює гіперпараметри моделі.
        Args:
            params: Нові параметри
        """
        self.logger.info(f"Setting parameters: {params}")
        self.model_params.update(params)

    def save(self, filepath: str) -> None:
        """
        Зберігає модель у файл.
        Args:
            filepath: шлях до файлу
        Raises:
            Exception: Якщо сталася помилка збереження
        """
        raise NotImplementedError("Save method must be implemented in subclass.")

    def load(self, filepath: str) -> None:
        """
        Завантажує модель з файлу.
        Args:
            filepath: шлях до файлу
        Raises:
            Exception: Якщо сталася помилка завантаження
        """
        raise NotImplementedError("Load method must be implemented in subclass.")

    def add_callback(self, callback: Callable) -> None:
        """
        Додає колбек для виклику під час навчання.
        Args:
            callback: Callable
        """
        self.callbacks.append(callback)
        self.logger.debug("Callback added.")

    def _run_callbacks(self, stage: str, **kwargs) -> None:
        """
        Викликає всі колбеки для даного етапу.
        Args:
            stage: Етап (наприклад, 'on_train_start')
            kwargs: Додаткові параметри
        """
        for cb in self.callbacks:
            try:
                cb(stage=stage, model=self, **kwargs)
            except Exception as e:
                self.logger.warning(f"Callback error at stage {stage}: {e}")

    def check_trained(self):
        """Викликає помилку, якщо модель не навчена."""
        if not self.is_trained:
            raise RuntimeError("Model is not trained yet.")

    def log_train_start(self, X_shape: Any, y_shape: Any):
        self.logger.info(f"Training started. X shape: {X_shape}, y shape: {y_shape}")

    def log_train_end(self):
        self.logger.info("Training finished.")

    def log_predict(self, X_shape: Any):
        self.logger.info(f"Prediction for input shape: {X_shape}")

    # Базова інтеграція з MLflow (опціонально, якщо встановлено)
    def log_mlflow(self, metrics: Dict[str, float], params: Optional[Dict[str, Any]] = None):
        try:
            import mlflow
            mlflow.log_params(params or self.model_params)
            mlflow.log_metrics(metrics)
            self.logger.info("Logged metrics and params to MLflow.")
        except ImportError:
            self.logger.debug("MLflow not installed; skipping MLflow logging.")
        except Exception as e:
            self.logger.warning(f"MLflow logging failed: {e}")
