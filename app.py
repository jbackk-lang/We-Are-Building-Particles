"""
Boundary-Matter TIMDR Dashboard
Rzeczywiste dane z Yahoo Finance przez API
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import requests
from datetime import datetime
import numpy as np

# ------------------ KONFIGURACJA STRONY ------------------
st.set_page_config(
    page_title="TIMDR – Rzeczywiste dane",
    page_icon="📈",
    layout="wide"
)

st.title("📊 TIMDR – Boundary-Matter Dashboard")
st.caption("Tryb: lewoskrętny (k = -0.75) | Dane rzeczywiste z Yahoo Finance przez API")

# ------------------ SIDEBAR ------------------
with st.sidebar:
    st.header("⚙️ Konfiguracja")
    
    symbol = st.text_input("Symbol giełdowy", value="EURPLN=X").upper()
    period = st.selectbox(
        "Okres danych",
        options=["1mo", "3mo", "6mo", "1y", "2y", "5y"],
        index=2
    )
    
    k = st.slider(
        "Siła skrętu (k)",
        min_value=-1.50,
        max_value=-0.50,
        value=-0.75,
        step=0.01,
        help="Parametr lewoskrętny – ujemne wartości opóźniają cykle"
    )
    
    api_url = st.text_input("Adres API", value="http://localhost:8000")
    
    fetch_btn = st.button("🔄 Pobierz dane", type="primary", use_container_width=True)

# ------------------ FUNKCJE ------------------
@st.cache_data(ttl=300)
def fetch_from_api(symbol: str, period: str, k: float, api_url: str):
    """Pobiera dane z API TIMDR."""
    try:
        response = requests.post(
            f"{api_url}/predict",
            json={"symbol": symbol, "period": period, "k": k},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Błąd API: {response.status_code} – {response.text}")
            return None
    except requests.exceptions.ConnectionError:
        st.error(f"❌ Nie można połączyć się z API na {api_url}. Uruchom api.py")
        return None
    except Exception as e:
        st.error(f"❌ Błąd: {e}")
        return None

@st.cache_data(ttl=300)
def fetch_ohlcv(symbol: str, period: str, api_url: str):
    """Pobiera surowe dane OHLCV z API."""
    try:
        response = requests.post(
            f"{api_url}/ohlcv",
            json={"symbol": symbol, "period": period, "k": -0.75},
            timeout=10
        )
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except:
        return None

# ------------------ POBIERANIE DANYCH ------------------
if fetch_btn:
    with st.spinner(f"Pobieranie {symbol} ({period}) z API..."):
        data = fetch_from_api(symbol, period, k, api_url)
        ohlcv = fetch_ohlcv(symbol, period, api_url)
        if data:
            st.session_state.data = data
            st.session_state.ohlcv = ohlcv
            st.success(f"✅ Pobrano dane dla {symbol}")
        else:
            st.session_state.data = None
            st.session_state.ohlcv = None

# ------------------ WYŚWIETLANIE ------------------
data = st.session_state.get("data")
ohlcv = st.session_state.get("ohlcv")

if data:
    # Podstawowe metryki
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Symbol", data["symbol"])
    col2.metric("Okres", data.get("period", "b.d."))
    col3.metric("Dni", data["metrics"]["days"])
    col4.metric("Ostatnia cena", f"${data['metrics']['last_price']:.2f}")
    
    change = data["metrics"]["change_pct"]
    col5.metric("Zmiana", f"{change:.2f}%", delta=change)
    
    st.divider()
    
    # ------------------ WYKRES CEN (prawdziwe dane) ------------------
    st.subheader("📈 Wykres cen zamknięcia")
    
    if ohlcv and len(ohlcv["dates"]) > 0:
        df_price = pd.DataFrame({
            "Data": pd.to_datetime(ohlcv["dates"]),
            "Cena": ohlcv["close"]
        })
        
        fig = px.line(
            df_price,
            x="Data",
            y="Cena",
            title=f"{data['symbol']} – cena zamknięcia",
            labels={"Cena": "Cena ($)", "Data": "Data"}
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Symulacja, jeśli brak danych OHLCV
        last_price = data["metrics"]["last_price"]
        days = 30
        dates = pd.date_range(end=datetime.now(), periods=days)
        prices = np.linspace(last_price * 0.9, last_price, days) + np.random.normal(0, 0.5, days)
        prices = np.maximum(prices, 0)
        
        df_price = pd.DataFrame({"Data": dates, "Cena": prices})
        fig = px.line(df_price, x="Data", y="Cena", title=f"{data['symbol']} – cena (symulacja)")
        st.plotly_chart(fig, use_container_width=True)
        st.caption("⚠️ Brak danych OHLCV – wyświetlono symulację")
    
    st.divider()
    
    # ------------------ METRYKI ------------------
    st.subheader(f"🧠 Metryki dla k = {data['k']:.2f}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("SMA 10", f"${data['metrics']['sma10']:.2f}")
    col2.metric("SMA 30", f"${data['metrics']['sma30']:.2f}")
    col3.metric("K (skręt)", f"{data['k']:.2f}")
    
    st.divider()
    
    # ------------------ TEZY ------------------
    st.subheader("🧠 Wygenerowane tezy")
    
    if "theses" in data:
        for thesis in data["theses"]:
            with st.expander(f"Teza {thesis['id']}: {thesis['type']} (Prawdopodobieństwo: {thesis['probability']}%)"):
                st.write(thesis["statement"])
                if thesis.get("action"):
                    st.info(f"**Rekomendacja:** {thesis['action']}")
                if thesis.get("entry"):
                    st.write(f"**Wejście:** {thesis['entry']} | **Stop-loss:** {thesis['stop_loss']} | **Take-profit:** {thesis['take_profit']}")
    
    st.divider()
    
    # ------------------ SYGNAŁ ------------------
    if "signal" in data:
        st.subheader("📊 Sygnał handlowy")
        signal = data["signal"]
        
        if signal["action"] == "KUP":
            st.success(f"🟢 {signal['action']} – {signal['probability']}% (cena: ${signal['price']:.2f})")
        elif signal["action"] == "SPRZEDAJ":
            st.error(f"🔴 {signal['action']} – {signal['probability']}% (cena: ${signal['price']:.2f})")
        else:
            st.warning(f"🟡 {signal['action']} – {signal['probability']}% (cena: ${signal['price']:.2f})")
    
    st.divider()

    # ------------------ TIMDR MARKET (twist/anomalia/trend/rytm) ------------------
    # Sygnaly z timdr_market.py, dolaczone przez api.py do odpowiedzi /predict
    # (klucz "timdr_market") - patrz compute_timdr_market_signals() w api.py.
    tm = data.get("timdr_market")
    if tm and "error" not in tm:
        st.subheader("🌀 Sygnały TIMDR Market")
        st.caption("Twist ceny (nagłe zmiany), anomalie wolumenu, trend lokalny, rytm wolumenu")

        trig = tm.get("trigger")
        if trig and trig.get("triggered"):
            loc_txt = f" (idx {trig['location']})" if trig.get("location") is not None else ""
            st.warning(f"🚨 **{trig['type']}**{loc_txt} — {trig['message']}")
        elif trig:
            st.caption("✅ Trigger: brak wykrytego zdarzenia sygnałowego.")

        col1, col2, col3 = st.columns(3)
        col1.metric("Twist (nagłe zmiany ceny)", tm["twist"]["count"])
        col2.metric("Anomalie wolumenu", tm["anomaly_volume"]["count"])

        trend = tm["trend"]
        if trend["direction"] == "rosnący":
            col3.metric("Trend lokalny", "📈 rosnący", f"{trend['current_slope']}")
        elif trend["direction"] == "malejący":
            col3.metric("Trend lokalny", "📉 malejący", f"{trend['current_slope']}")
        else:
            col3.metric("Trend lokalny", "➖ płaski" if trend["direction"] else "b.d.")

        rhythm = tm["rhythm_volume"]
        if rhythm["dominant_periods"]:
            st.info(
                f"🔁 Wykryto okresowość wolumenu: co ~{', '.join(str(p) for p in rhythm['dominant_periods'])} "
                f"świec (siła: {rhythm['beacon_score']:.2f})"
            )

        if tm["twist"]["recent"]:
            with st.expander(f"Ostatnie sygnały twist ({tm['twist']['count']} łącznie)"):
                for p in tm["twist"]["recent"]:
                    st.write(f"**{p['date']}** — z={p['z']}")

        if tm["anomaly_volume"]["recent"]:
            with st.expander(f"Ostatnie anomalie wolumenu ({tm['anomaly_volume']['count']} łącznie)"):
                for p in tm["anomaly_volume"]["recent"]:
                    st.write(f"**{p['date']}** — z={p['z']}")

        st.caption(
            "⚠️ TIMDRMarket to sygnały statystyczne (MAD-zscore), nie prognoza - "
            "punkty 'twist'/'anomalia' oznaczają że coś odbiegało od niedawnej normy, "
            "nie że to sygnał kupna/sprzedaży."
        )
    elif tm and "error" in tm:
        st.caption(f"⚠️ TIMDR Market: {tm['error']}")

    st.divider()
    st.caption(f"Ostatnia aktualizacja: {data.get('timestamp', 'b.d.')}")

else:
    st.info("👈 Wybierz symbol i kliknij 'Pobierz dane', lub upewnij się, że API działa na http://localhost:8000")

# ------------------ STOPKA ------------------
st.divider()
st.caption("Boundary-Matter / TIMDR Framework | Dane z Yahoo Finance przez API")