# timdr_market_trigger.py
# ============================================
# TIMDR Market Trigger Module
# ============================================
#
# ROLA: dispatcher sygnałowy — NIE liczy własnej statystyki. Zapytuje już
# przetestowany TIMDRMarket (timdr_market.py, 18/18 testów) i mapuje jego
# rozłączne wyniki (twist_price/anomaly_volume/rhythm_volume) na jedno,
# priorytetyzowane zdarzenie z lokalizacją. ZASTANY STAN: api.py::
# compute_timdr_market_signals() już liczy te trzy sygnały, ale wystawia
# je jako trzy równoległe, nieuszeregowane pola w JSON ("twist",
# "anomaly_volume", "rhythm_volume") — ten sam wzorzec braku dispatchera,
# co wcześniej w TIMDR-Industrial-Predict przed timdr_industrial_trigger.py.
#
# `trend_price()` ŚWIADOMIE NIE jest tu użyty: zwraca ciągłą tablicę
# nachyleń (slopes/z) dla KAŻDEJ świecy, nie listę zdarzeń/indeksów jak
# twist_price()/anomaly_volume() — to metryka ciągła (kierunek trendu),
# nie detektor dyskretnego zdarzenia z jednoznaczną lokalizacją, więc nie
# ma czym "wyzwolić" triggera bez wymyślania nowego, niezweryfikowanego
# progu (czego ten dispatcher ma unikać z zasady).
#
# Priorytet: STRUCTURE (twist_price — nagłe załamanie kierunku ceny,
# druga pochodna, najbardziej gwałtowny i najkrótszy w czasie sygnał) >
# ANOMALY_VOLUME (anomaly_volume — pojedynczy nietypowy wolumen) > RHYTHM
# (rhythm_volume — wykryta okresowość wolumenu; informacyjna właściwość
# całej serii, nie "coś złego się stało", więc najniższy priorytet i bez
# lokalizacji punktowej) > NONE.

from enum import Enum

from timdr_market import TIMDRMarket


class MarketTriggerType(Enum):
    STRUCTURE = "structure_twist"
    ANOMALY_VOLUME = "anomaly_volume"
    RHYTHM = "rhythm_volume"
    NONE = "none"


class MarketTriggerResult:
    def __init__(self, triggered=False, trigger_type=MarketTriggerType.NONE,
                 location=None, message=""):
        self.triggered = triggered
        self.trigger_type = trigger_type
        self.location = location
        self.message = message

    def as_dict(self):
        return {
            "triggered": self.triggered,
            "type": self.trigger_type.value,
            "location": self.location,
            "message": self.message,
        }


class MarketTrigger:
    """
    Dispatcher nad TIMDRMarket.twist_price()/anomaly_volume()/
    rhythm_volume(). `market` można wstrzyknąć (np. w testach) - domyślnie
    tworzy prawdziwy TIMDRMarket().

    UWAGA: `twist_price()`/`anomaly_volume()` mają WŁASNE, zakodowane na
    stałe progi (3.5 / 3.0 odchylenia MAD) - tak jak w
    timdr_industrial_trigger.py, ten dispatcher świadomie NIE przyjmuje
    parametrów progowych, których i tak nie dałoby się przekazać dalej
    (martwy parametr konstruktora - błąd znaleziony wcześniej w
    TIMDR-Security-Module). `rhythm_power_thresh`/`rhythm_max_lag`
    przekazywane do `rhythm_volume()` to jedyne realnie dostrajalne progi.
    """

    def __init__(self, rhythm_max_lag=60, rhythm_power_thresh=0.4, market=None):
        self.market = market if market is not None else TIMDRMarket()
        self.rhythm_max_lag = rhythm_max_lag
        self.rhythm_power_thresh = rhythm_power_thresh
        self.last_result = MarketTriggerResult()

    def analyze(self, candles):
        twist_idx, _twist_z = self.market.twist_price(candles)
        if len(twist_idx):
            loc = int(twist_idx[-1])  # najnowsze (ostatnie) zdarzenie jest najistotniejsze dla monitoringu na zywo
            return self._set_result(
                True, MarketTriggerType.STRUCTURE, loc,
                "Nagłe załamanie kierunku ceny (twist)."
            )

        anomaly_idx, _anomaly_z = self.market.anomaly_volume(candles)
        if len(anomaly_idx):
            loc = int(anomaly_idx[-1])
            return self._set_result(
                True, MarketTriggerType.ANOMALY_VOLUME, loc,
                "Nietypowy wolumen względem niedawnej normy."
            )

        periods, score = self.market.rhythm_volume(
            candles, max_lag=self.rhythm_max_lag, power_thresh=self.rhythm_power_thresh,
        )
        if periods:
            return self._set_result(
                True, MarketTriggerType.RHYTHM, None,
                f"Wykryta okresowość wolumenu: co ~{periods[0]} świec (siła {score:.2f})."
            )

        return self._set_result(
            False, MarketTriggerType.NONE, None,
            "Brak wykrytego zdarzenia sygnałowego."
        )

    def _set_result(self, triggered, trigger_type, location, message):
        self.last_result = MarketTriggerResult(triggered, trigger_type, location, message)
        return self.last_result

    def get_last(self):
        return self.last_result
