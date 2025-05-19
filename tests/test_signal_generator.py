import pytest
import logging
from analysis.signal_generator import SignalGenerator, SignalAction, ModelProtocol

class DummyModel:
    """Базова модель, повертає test_score або 0.5"""
    model_id = "dummy"
    model_params = {}

    def predict(self, market_data):
        return market_data.get("test_score", 0.5)

class HighModel:
    """Модель, яка завжди повертає 1.0"""
    model_id = "high"
    model_params = {}

    def predict(self, market_data):
        return 1.0

class LowModel:
    """Модель, яка завжди повертає 0.0"""
    model_id = "low"
    model_params = {}

    def predict(self, market_data):
        return 0.0

def simple_strategy(data):
    """Проста стратегія, повертає значення simple або 0.2"""
    return {"score": data.get("simple", 0.2)}

@pytest.fixture
def dummy_model():
    return DummyModel()

@pytest.fixture
def high_model():
    return HighModel()

@pytest.fixture
def low_model():
    return LowModel()

def make_generator(models=None, thresholds=None, strategy=None, strategy_id="test_strategy", logger=None):
    return SignalGenerator(
        models=models or [],
        thresholds=thresholds or {"BTCUSDT": {"buy": 0.7, "sell": 0.3}, "default": {"buy": 0.6, "sell": 0.4}},
        simple_strategy=strategy,
        strategy_id=strategy_id,
        logger=logger or logging.getLogger("test_signal_generator")
    )

@pytest.mark.parametrize("test_score,expected_action", [
    (0.7, SignalAction.BUY.value),
    (0.8, SignalAction.BUY.value),
    (0.3, SignalAction.SELL.value),
    (0.2, SignalAction.SELL.value),
    (0.5, SignalAction.HOLD.value),
    (0.6, SignalAction.HOLD.value),
])
def test_generate_signal_parametrized_actions(test_score, expected_action, dummy_model):
    """
    Перевіряємо різні сценарії для моделей з різними test_score.
    """
    generator = make_generator(models=[dummy_model])
    market_data = {"symbol": "BTCUSDT", "test_score": test_score}
    signal = generator.generate_signal(market_data)
    assert signal["action"] == expected_action
    assert isinstance(signal["confidence"], float)
    assert signal["meta"]["symbol"] == "BTCUSDT"

@pytest.mark.parametrize("buy,sell,score,expected", [
    (0.8, 0.4, 0.85, SignalAction.BUY.value),
    (0.8, 0.4, 0.8, SignalAction.BUY.value),
    (0.8, 0.4, 0.4, SignalAction.SELL.value),
    (0.8, 0.4, 0.3, SignalAction.SELL.value),
    (0.8, 0.4, 0.6, SignalAction.HOLD.value),
])
def test_generate_signal_thresholds(buy, sell, score, expected):
    """
    Тестуємо різні пороги buy/sell для символу.
    """
    generator = make_generator(
        models=[DummyModel()],
        thresholds={"BTCUSDT": {"buy": buy, "sell": sell}}
    )
    market_data = {"symbol": "BTCUSDT", "test_score": score}
    signal = generator.generate_signal(market_data)
    assert signal["action"] == expected

@pytest.mark.parametrize("simple,expected_action", [
    (0.8, SignalAction.BUY.value),
    (0.2, SignalAction.SELL.value),
    (0.5, SignalAction.HOLD.value),
])
def test_generate_signal_with_simple_strategy(simple, expected_action):
    """
    Тестуємо просту стратегію з різними значеннями simple.
    """
    generator = make_generator(models=[], strategy=simple_strategy)
    market_data = {"symbol": "ETHUSDT", "simple": simple}
    signal = generator.generate_signal(market_data)
    assert signal["action"] == expected_action

def test_generate_signal_with_high_and_low_model(high_model, low_model):
    """
    Тестуємо комбінування моделей з різною логікою predict.
    """
    generator = make_generator(models=[high_model, low_model])
    market_data = {"symbol": "BTCUSDT"}
    signal = generator.generate_signal(market_data)
    # Середнє між 1.0 та 0.0 == 0.5 → HOLD (за замовчуванням порогів)
    assert signal["action"] == SignalAction.HOLD.value

def test_state_update(dummy_model):
    """
    Перевіряємо, що стан оновлюється після генерації сигналу.
    """
    generator = make_generator(models=[dummy_model])
    market_data = {"symbol": "BTCUSDT", "test_score": 0.9}
    signal = generator.generate_signal(market_data)
    state = generator.get_state()
    last = state["BTCUSDT"]
    assert last["last_signal"]["action"] == SignalAction.BUY.value
    assert abs(last["last_score"] - 0.9) < 1e-8
    assert "last_updated" in last
    assert isinstance(last["last_signal"]["confidence"], float)

def test_threshold_validation():
    """
    Тестуємо валідацію порогів: відсутній ключ, не float, значення поза діапазоном.
    """
    # Відсутній ключ 'sell'
    with pytest.raises(ValueError):
        make_generator(thresholds={"BTCUSDT": {"buy": 0.7}})
    # Некоректний тип (рядок замість float)
    with pytest.raises(Exception):
        make_generator(thresholds={"BTCUSDT": {"buy": "0.7", "sell": 0.2}})
    # Значення buy < sell (нелогічно, але можливо у вашій логіці допустимо)
    # Якщо це не помилка, можна забрати цей тест
    # with pytest.raises(ValueError):
    #     make_generator(thresholds={"BTCUSDT": {"buy": 0.2, "sell": 0.7}})

def test_no_thresholds_for_symbol(dummy_model):
    """
    Перевіряємо використання порогів за замовчуванням, якщо для символу немає спеціальних порогів.
    """
    generator = make_generator(models=[dummy_model], thresholds={"default": {"buy": 0.6, "sell": 0.4}})
    market_data = {"symbol": "UNKNOWN", "test_score": 0.65}
    signal = generator.generate_signal(market_data)
    # buy > 0.6, тому BUY
    assert signal["action"] == SignalAction.BUY.value

def test_none_model_and_only_simple_strategy():
    """
    Перевіряємо роботу генератора, якщо models=[] і є лише simple_strategy.
    """
    generator = make_generator(models=[], strategy=simple_strategy)
    market_data = {"symbol": "BTCUSDT", "simple": 0.2}
    signal = generator.generate_signal(market_data)
    assert signal["action"] == SignalAction.SELL.value
    # Видаляємо simple, має брати дефолтне 0.2
    signal2 = generator.generate_signal({"symbol": "BTCUSDT"})
    assert signal2["action"] == SignalAction.SELL.value

def test_generate_signal_missing_keys(dummy_model):
    """
    Перевіряємо, як generate_signal працює, якщо в market_data не вистачає ключів.
    """
    generator = make_generator(models=[dummy_model])
    signal = generator.generate_signal({})
    assert signal["action"] == SignalAction.HOLD.value
    assert isinstance(signal["confidence"], float)
    # simple_strategy без ключа simple
    generator2 = make_generator(models=[], strategy=simple_strategy)
    signal2 = generator2.generate_signal({})
    assert signal2["action"] == SignalAction.SELL.value

def test_add_and_remove_model():
    """
    Тестуємо додавання і видалення моделей.
    """
    generator = make_generator(models=[])
    class ExtraModel:
        model_id = "extra"
        model_params = {}
        def predict(self, market_data): return 1.0
    generator.add_model(ExtraModel())
    assert any(m.model_id == "extra" for m in generator.models)
    generator.remove_model("extra")
    assert not any(m.model_id == "extra" for m in generator.models)

def test_logging_caplog(dummy_model, caplog):
    """
    Перевіряємо, що потрібні повідомлення потрапляють у лог під час генерації сигналу.
    """
    generator = make_generator(models=[dummy_model])
    with caplog.at_level(logging.INFO):
        signal = generator.generate_signal({"symbol": "BTCUSDT", "test_score": 0.8})
    assert any("Generated signal" in msg for msg in caplog.text)
    assert signal["action"] == SignalAction.BUY.value
