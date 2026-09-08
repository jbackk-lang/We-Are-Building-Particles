# test_timdr_market_trigger.py
"""
Testy dla timdr_market_trigger.py (MarketTrigger).

1. Cztery testy integracyjne na PRAWDZIWYM TIMDRMarket (bez mockowania),
   z fixturami analogicznymi do tych z test_timdr_market.py (skok ceny,
   skok wolumenu, znana okresowość wolumenu, cisza) - potwierdzają, że
   dispatcher faktycznie odpala się na realnej matematyce, nie tylko na
   zaślepkach.
2. Testy priorytetów z wstrzykniętym `_FakeMarket` - testują WYŁĄCZNIE
   logikę mapowania/priorytetów dispatchera.
"""
import numpy as np
import pytest

from timdr_market import TIMDRMarket
from timdr_market_trigger import MarketTrigger, MarketTriggerType


def make_candles(close, volume, t=None):
    close = np.asarray(close, dtype=float)
    volume = np.asarray(volume, dtype=float)
    n = len(close)
    if t is None:
        t = np.arange(n, dtype=float)
    return np.column_stack([close, close, close, close, volume, t])


# ----------------------------------------------------------------------
# 1) Testy integracyjne na realnym TIMDRMarket
# ----------------------------------------------------------------------

def test_structure_na_realnym_skoku_ceny():
    """Ten sam fixture co test_twist_detects_obvious_price_spike w
    test_timdr_market.py: 55 świec plaskich + 5 rosnacych do +30. Plaski
    wolumen -> anomaly_volume() pusty, wiec STRUCTURE musi wygrac."""
    close = np.concatenate([np.full(55, 100.0), np.linspace(100, 130, 5)])
    candles = make_candles(close, np.full(60, 1000.0))

    market = TIMDRMarket()
    twist_idx, _ = market.twist_price(candles)
    assert len(twist_idx) > 0  # sanity - dowod, ze fixture faktycznie odpala twist
    anomaly_idx, _ = market.anomaly_volume(candles)
    assert len(anomaly_idx) == 0  # sanity - dowod, ze to naprawde STRUCTURE, nie ANOMALY_VOLUME

    result = MarketTrigger().analyze(candles)
    assert result.triggered is True
    assert result.trigger_type == MarketTriggerType.STRUCTURE
    assert result.location == int(twist_idx[-1])


def test_anomaly_volume_gdy_nie_ma_twista():
    """Ten sam fixture co test_anomaly_volume_detects_obvious_spike:
    plaska cena (twist_price zawsze pusty), pojedynczy skok wolumenu x50
    w idx=30."""
    close = np.full(60, 100.0)
    vol = np.full(60, 1000.0)
    vol[30] = 50000.0
    candles = make_candles(close, vol)

    market = TIMDRMarket()
    assert len(market.twist_price(candles)[0]) == 0  # sanity

    result = MarketTrigger().analyze(candles)
    assert result.triggered is True
    assert result.trigger_type == MarketTriggerType.ANOMALY_VOLUME
    assert result.location == 30


def test_rhythm_gdy_nie_ma_innych():
    """Ten sam fixture co test_detects_known_period w test_timdr_market.py:
    plaska cena (twist_price pusty), sinusoidalny wolumen o okresie 20
    (amplituda 500 wokol 1000 - zbyt gladka/ograniczona, by przekroczyc
    prog anomaly_volume()=3.0: dla arcsine-rozkladu |sin|, mediana
    odchylenia to ok. 0.7071*500=353.55*1.4826=524.3, max z=500/524.3=
    0.95<3.0)."""
    n = 300
    period = 20
    t = np.arange(n, dtype=float)
    vol = 1000 + 500 * np.sin(2 * np.pi * t / period)
    candles = make_candles(np.full(n, 100.0), vol, t)

    market = TIMDRMarket()
    assert len(market.twist_price(candles)[0]) == 0  # sanity - cena plaska
    assert len(market.anomaly_volume(candles)[0]) == 0  # sanity - patrz uzasadnienie wyzej

    result = MarketTrigger().analyze(candles)
    assert result.triggered is True
    assert result.trigger_type == MarketTriggerType.RHYTHM
    assert result.location is None
    assert "20" in result.message


def test_none_gdy_wszystko_ciche():
    candles = make_candles(np.full(60, 100.0), np.full(60, 1000.0))
    result = MarketTrigger().analyze(candles)
    assert result.triggered is False
    assert result.trigger_type == MarketTriggerType.NONE
    assert result.location is None


# ----------------------------------------------------------------------
# 2) Testy priorytetów z wstrzyknietym _FakeMarket
# ----------------------------------------------------------------------

class _FakeMarket:
    def __init__(self, twist_idx=None, anomaly_idx=None, rhythm_periods=None, rhythm_score=0.0):
        self._twist_idx = np.array(twist_idx or [], dtype=int)
        self._anomaly_idx = np.array(anomaly_idx or [], dtype=int)
        self._rhythm_periods = rhythm_periods or []
        self._rhythm_score = rhythm_score

    def twist_price(self, candles):
        return self._twist_idx, np.zeros_like(self._twist_idx, dtype=float)

    def anomaly_volume(self, candles):
        return self._anomaly_idx, np.zeros_like(self._anomaly_idx, dtype=float)

    def rhythm_volume(self, candles, max_lag=60, power_thresh=0.4):
        return self._rhythm_periods, self._rhythm_score


def test_priorytet_structure_nad_anomaly_i_rhythm():
    market = _FakeMarket(twist_idx=[5], anomaly_idx=[1], rhythm_periods=[20])
    result = MarketTrigger(market=market).analyze(candles=None)
    assert result.trigger_type == MarketTriggerType.STRUCTURE
    assert result.location == 5


def test_priorytet_anomaly_nad_rhythm():
    market = _FakeMarket(anomaly_idx=[7], rhythm_periods=[20])
    result = MarketTrigger(market=market).analyze(candles=None)
    assert result.trigger_type == MarketTriggerType.ANOMALY_VOLUME
    assert result.location == 7


def test_lokalizacja_to_ostatni_indeks_gdy_wiele_zdarzen():
    """Dla monitoringu na zywo najnowsze (ostatnie) zdarzenie jest
    najistotniejsze - dispatcher bierze idx[-1], nie idx[0]."""
    market = _FakeMarket(twist_idx=[2, 9, 40])
    result = MarketTrigger(market=market).analyze(candles=None)
    assert result.location == 40


def test_get_last_zwraca_ostatni_wynik():
    market = _FakeMarket(anomaly_idx=[3])
    trigger = MarketTrigger(market=market)
    result = trigger.analyze(candles=None)
    assert trigger.get_last() is result
