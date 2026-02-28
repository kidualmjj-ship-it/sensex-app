import time
from io import StringIO

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


# =========================
# Utility functions
# =========================
def to_float(x, default=np.nan):
    try:
        if pd.isna(x):
            return default
        if isinstance(x, str):
            x = x.replace(",", "").strip()
        return float(x)
    except Exception:
        return default


def safe_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def ema(series, span=20):
    return series.ewm(span=span, adjust=False).mean()


def detect_trend(df):
    """
    Simple trend marker:
    - EMA20 vs EMA50 + EMA20 slope
    """
    if df is None or df.empty or len(df) < 60:
        return "CHOP"

    close = df["close"]
    e20 = ema(close, 20)
    e50 = ema(close, 50)
    slope = e20.iloc[-1] - e20.iloc[-10] if len(e20) >= 10 else 0

    if e20.iloc[-1] > e50.iloc[-1] and slope > 0:
        return "UP"
    if e20.iloc[-1] < e50.iloc[-1] and slope < 0:
        return "DOWN"
    return "CHOP"


def intraday_levels(df, lookback=60):
    """
    Support/Resistance from recent swing window.
    """
    if df is None or df.empty:
        return None, None
    recent = df.tail(min(lookback, len(df)))
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    return support, resistance


def detect_break_retest(df_1m, level, direction):
    """
    Break + Retest trigger (practical):
    - UP: prev close > level, last candle low touches near level, last close > level
    - DOWN: prev close < level, last candle high touches near level, last close < level
    """
    if df_1m is None or df_1m.empty or len(df_1m) < 5 or level is None:
        return False

    prev = df_1m.iloc[-2]
    last = df_1m.iloc[-1]

    if direction == "UP":
        breakout_context = prev["close"] > level
        retest_hold = (last["low"] <= level * 1.0005) and (last["close"] > level)
        return bool(breakout_context and retest_hold)

    if direction == "DOWN":
        breakdown_context = prev["close"] < level
        retest_fail = (last["high"] >= level * 0.9995) and (last["close"] < level)
        return bool(breakdown_context and retest_fail)

    return False


def parse_candles_csv(file_or_text):
    """
    Accepts uploaded CSV file or pasted CSV text.
    Must contain open/high/low/close. time optional, volume optional.
    """
    if isinstance(file_or_text, str):
        df = pd.read_csv(StringIO(file_or_text))
    else:
        df = pd.read_csv(file_or_text)

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    col_open = safe_col(df, ["open", "o"])
    col_high = safe_col(df, ["high", "h"])
    col_low = safe_col(df, ["low", "l"])
    col_close = safe_col(df, ["close", "c", "ltp"])
    col_time = safe_col(df, ["time", "timestamp", "date", "datetime"])
    col_vol = safe_col(df, ["volume", "vol", "v"])

    if not (col_open and col_high and col_low and col_close):
        raise ValueError("Candles CSV must include open/high/low/close columns.")

    df = df.rename(columns={
        col_open: "open",
        col_high: "high",
        col_low: "low",
        col_close: "close"
    })

    for k in ["open", "high", "low", "close"]:
        df[k] = df[k].apply(to_float)

    if col_time:
        df = df.rename(columns={col_time: "time"})
    else:
        df["time"] = np.arange(len(df))  # fallback

    if col_vol:
        df = df.rename(columns={col_vol: "volume"})
        df["volume"] = df["volume"].apply(to_float)
    else:
        df["volume"] = 0.0

    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    return df


def parse_option_chain_csv(file_or_text):
    """
    Expected columns (flexible):
    strike, call_oi, put_oi (required)
    optional: call_oi_chg, put_oi_chg, call_ltp, put_ltp
    """
    if isinstance(file_or_text, str):
        df = pd.read_csv(StringIO(file_or_text))
    else:
        df = pd.read_csv(file_or_text)

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    strike = safe_col(df, ["strike", "strike_price", "sp", "strk"])
    call_oi = safe_col(df, ["call_oi", "ce_oi", "oi_ce", "ceoi"])
    put_oi = safe_col(df, ["put_oi", "pe_oi", "oi_pe", "peoi"])

    if not (strike and call_oi and put_oi):
        raise ValueError("Option chain must include Strike + Call OI + Put OI columns.")

    out = pd.DataFrame({
        "strike": df[strike].apply(to_float),
        "call_oi": df[call_oi].apply(to_float),
        "put_oi": df[put_oi].apply(to_float),
    })

    # Optional columns
    call_oi_chg = safe_col(df, ["call_oi_chg", "ce_oi_chg", "call_change_oi", "ce_change_oi"])
    put_oi_chg = safe_col(df, ["put_oi_chg", "pe_oi_chg", "put_change_oi", "pe_change_oi"])
    call_ltp = safe_col(df, ["call_ltp", "ce_ltp", "call_price", "ce_price"])
    put_ltp = safe_col(df, ["put_ltp", "pe_ltp", "put_price", "pe_price"])

    if call_oi_chg:
        out["call_oi_chg"] = df[call_oi_chg].apply(to_float)
    if put_oi_chg:
        out["put_oi_chg"] = df[put_oi_chg].apply(to_float)
    if call_ltp:
        out["call_ltp"] = df[call_ltp].apply(to_float)
    if put_ltp:
        out["put_ltp"] = df[put_ltp].apply(to_float)

    out = out.dropna(subset=["strike"]).sort_values("strike").reset_index(drop=True)
    return out


def chain_stats(chain_df):
    total_call = chain_df["call_oi"].sum()
    total_put = chain_df["put_oi"].sum()
    pcr = (total_put / total_call) if total_call else np.nan

    max_call_row = chain_df.loc[chain_df["call_oi"].idxmax()]
    max_put_row = chain_df.loc[chain_df["put_oi"].idxmax()]

    return {
        "pcr": float(pcr) if np.isfinite(pcr) else np.nan,
        "max_call_oi_strike": float(max_call_row["strike"]),
        "max_put_oi_strike": float(max_put_row["strike"])
    }


def pick_atm_itm(spot, strikes):
    strikes = np.array(sorted([s for s in strikes if np.isfinite(s)]))
    if len(strikes) == 0 or not np.isfinite(spot) or spot <= 0:
        return np.nan, np.nan, np.nan, np.nan

    atm = strikes[np.argmin(np.abs(strikes - spot))]
    step = float(np.median(np.diff(strikes))) if len(strikes) > 1 else 100.0
    itm_ce = atm - step
    itm_pe = atm + step
    return float(atm), float(itm_ce), float(itm_pe), float(step)


def recommendation_engine(df_5m, df_1m, chain_df, pcr_low=0.8, pcr_high=1.4, level_lookback=60):
    """
    Returns: (ACTION, REASON, KEY_LEVEL, TREND, SUPPORT, RESISTANCE, PCR)
    ACTION in: BUY_CALL, BUY_PUT, NO_TRADE
    """
    if df_5m is None or df_1m is None or df_5m.empty or df_1m.empty:
        return "NO_TRADE", "Upload both 5m and 1m candles", None, "CHOP", None, None, np.nan

    trend = detect_trend(df_5m)
    support, resistance = intraday_levels(df_5m, lookback=level_lookback)

    pcr = np.nan
    if chain_df is not None and not chain_df.empty:
        pcr = chain_stats(chain_df)["pcr"]

    if trend == "UP":
        if np.isfinite(pcr) and pcr < pcr_low:
            return "NO_TRADE", f"UP trend but PCR too low ({pcr:.2f})", None, trend, support, resistance, pcr
        if detect_break_retest(df_1m, resistance, "UP"):
            return "BUY_CALL", f"UP trend + Break&Retest above R={resistance:.0f} (PCR={pcr:.2f})", resistance, trend, support, resistance, pcr

    if trend == "DOWN":
        if np.isfinite(pcr) and pcr > pcr_high:
            return "NO_TRADE", f"DOWN trend but PCR too high ({pcr:.2f})", None, trend, support, resistance, pcr
        if detect_break_retest(df_1m, support, "DOWN"):
            return "BUY_PUT", f"DOWN trend + Break&Retest below S={support:.0f} (PCR={pcr:.2f})", support, trend, support, resistance, pcr

    return "NO_TRADE", f"Trend={trend} or no clean Break&Retest", None, trend, support, resistance, pcr


def js_alert(text: str):
    components.html(
        f"""
        <script>
          alert({text!r});
        </script>
        """,
        height=0,
    )


# =========================
# Streamlit App
# =========================
st.set_page_config(page_title="SENSEX Call/Put Signal App", layout="wide")
st.title("SENSEX Call/Put Signal App (Manual Trading)")
st.caption("Upload/paste candles + option chain → app pops up BUY CALL / BUY PUT when signal appears.")

if "last_action" not in st.session_state:
    st.session_state.last_action = "NO_TRADE"
if "last_popup_ts" not in st.session_state:
    st.session_state.last_popup_ts = 0.0

st.sidebar.header("Manual Inputs")
spot = st.sidebar.number_input("SENSEX Spot (manual)", min_value=0.0, value=0.0, step=10.0)
ce_ltp = st.sidebar.number_input("Selected CE LTP (manual)", min_value=0.0, value=0.0, step=1.0)
pe_ltp = st.sidebar.number_input("Selected PE LTP (manual)", min_value=0.0, value=0.0, step=1.0)

st.sidebar.header("Signal Settings")
level_lookback = st.sidebar.slider("Support/Resistance lookback (5m candles)", 20, 200, 60)
pcr_low = st.sidebar.slider("PCR minimum for CALL bias", 0.50, 1.20, 0.80, 0.05)
pcr_high = st.sidebar.slider("PCR maximum for PUT bias", 0.80, 2.00, 1.40, 0.05)

st.sidebar.header("Risk (Premium-based)")
sl_pct = st.sidebar.slider("Stop loss %", 0.05, 0.50, 0.25, 0.01)
tgt_pct = st.sidebar.slider("Target %", 0.10, 1.50, 0.60, 0.01)

st.sidebar.header("Popup Controls")
popup_style = st.sidebar.selectbox("Popup Type", ["Toast (recommended)", "Browser Alert (hard popup)"])
cooldown_sec = st.sidebar.slider("Popup cooldown (seconds)", 10, 300, 60, 10)
auto_refresh = st.sidebar.toggle("Auto Refresh", value=False)
refresh_sec = st.sidebar.slider("Refresh seconds", 1, 30, 5)

tabs = st.tabs(["📈 Live Monitor", "⛓️ Option Chain", "🧪 Backtest", "🚨 Signal Panel"])

with tabs[0]:
    st.subheader("Live Monitor (manual spot + premium + candle upload)")

    c1, c2, c3 = st.columns(3)
    c1.metric("SENSEX Spot", f"{spot:,.2f}" if spot else "—")
    c2.metric("CE LTP", f"{ce_ltp:,.2f}" if ce_ltp else "—")
    c3.metric("PE LTP", f"{pe_ltp:,.2f}" if pe_ltp else "—")

    st.markdown("### Upload 5-minute candles (for trend + support/resistance)")
    st.file_uploader("Upload 5m candles CSV", type=["csv"], key="c5m")

    st.markdown("### Upload 1-minute candles (for break+retest trigger)")
    st.file_uploader("Upload 1m candles CSV", type=["csv"], key="c1m")

    st.markdown("### Premium SL/Target (for manual trade)")
    if ce_ltp > 0:
        st.write(f"**CE** SL: ₹{ce_ltp*(1-sl_pct):.2f} | Target: ₹{ce_ltp*(1+tgt_pct):.2f}")
    if pe_ltp > 0:
        st.write(f"**PE** SL: ₹{pe_ltp*(1-sl_pct):.2f} | Target: ₹{pe_ltp*(1+tgt_pct):.2f}")

with tabs[1]:
    st.subheader("Option Chain (paste/upload CSV) → PCR + OI Walls + Strike Picker")

    st.file_uploader("Upload option chain CSV", type=["csv"], key="chainfile")
    pasted_chain = st.text_area(
        "Or paste option chain CSV here",
        height=160,
        placeholder="strike,call_oi,put_oi,call_oi_chg,put_oi_chg,call_ltp,put_ltp",
        key="chainpaste"
    )

    chain_df = None
    try:
        if st.session_state.get("chainfile") is not None:
            chain_df = parse_option_chain_csv(st.session_state.get("chainfile"))
        elif pasted_chain.strip():
            chain_df = parse_option_chain_csv(pasted_chain)

        if chain_df is not None and not chain_df.empty:
            stats = chain_stats(chain_df)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("PCR", f"{stats['pcr']:.2f}" if np.isfinite(stats["pcr"]) else "—")
            c2.metric("Max Call OI Strike", f"{stats['max_call_oi_strike']:.0f}")
            c3.metric("Max Put OI Strike", f"{stats['max_put_oi_strike']:.0f}")
            c4.metric("Bias (simple)", "Bullish" if np.isfinite(stats["pcr"]) and stats["pcr"] > 1.0 else "Bearish")

            if spot > 0:
                atm, itm_ce, itm_pe, step = pick_atm_itm(spot, chain_df["strike"].tolist())
                st.success(
                    f"Strike Picker: ATM **{atm:.0f}** | ITM CE **{itm_ce:.0f}** | ITM PE **{itm_pe:.0f}** | step≈{step:.0f}"
                )

            st.dataframe(chain_df, use_container_width=True)

    except Exception as e:
        st.error(f"Option chain error: {e}")

with tabs[2]:
    st.subheader("Backtest (simple breakout model on uploaded candles)")
    st.caption("Index-only backtest. Upload any candle CSV with open/high/low/close.")

    bt_file = st.file_uploader("Upload candles CSV for backtest (1m/5m)", type=["csv"], key="btfile")

    if bt_file:
        try:
            df_bt = parse_candles_csv(bt_file)
            lookback = st.slider("Level Lookback (candles)", 10, 200, 60, key="bt_lb")
            rr = st.slider("RR (Target = Risk*RR)", 1.0, 3.0, 2.0, 0.1, key="bt_rr")
            stop_points = st.number_input("Stop (index points)", min_value=20, value=120, step=10, key="bt_sl")
            target_points = stop_points * rr

            trades = []
            in_pos = False
            direction = None
            entry = sl = tp = None

            for i in range(lookback, len(df_bt)):
                window = df_bt.iloc[i-lookback:i]
                prev_high = window["high"].max()
                prev_low = window["low"].min()

                price = df_bt.loc[i, "close"]
                hi = df_bt.loc[i, "high"]
                lo = df_bt.loc[i, "low"]

                if not in_pos:
                    if price > prev_high:
                        in_pos = True
                        direction = "LONG"
                        entry = price
                        sl = entry - stop_points
                        tp = entry + target_points
                        trades.append({"i": i, "dir": "LONG", "entry": entry, "sl": sl, "tp": tp, "exit": None, "R": None})
                    elif price < prev_low:
                        in_pos = True
                        direction = "SHORT"
                        entry = price
                        sl = entry + stop_points
                        tp = entry - target_points
                        trades.append({"i": i, "dir": "SHORT", "entry": entry, "sl": sl, "tp": tp, "exit": None, "R": None})
                else:
                    t = trades[-1]
                    if direction == "LONG":
                        if lo <= sl:
                            t["exit"] = sl
                            t["R"] = -1
                            in_pos = False
                        elif hi >= tp:
                            t["exit"] = tp
                            t["R"] = rr
                            in_pos = False
                    else:
                        if hi >= sl:
                            t["exit"] = sl
                            t["R"] = -1
                            in_pos = False
                        elif lo <= tp:
                            t["exit"] = tp
                            t["R"] = rr
                            in_pos = False

            tdf = pd.DataFrame(trades).dropna(subset=["R"])
            if tdf.empty:
                st.warning("No completed trades in backtest with these settings.")
            else:
                win_rate = (tdf["R"] > 0).mean() * 100
                expectancy = tdf["R"].mean()
                c1, c2, c3 = st.columns(3)
                c1.metric("Trades", f"{len(tdf)}")
                c2.metric("Win rate", f"{win_rate:.1f}%")
                c3.metric("Avg R", f"{expectancy:.2f}R")
                st.dataframe(tdf.tail(50), use_container_width=True)

        except Exception as e:
            st.error(f"Backtest error: {e}")

with tabs[3]:
    st.subheader("Signal Panel (BUY CALL / BUY PUT popup)")

    df_5m = None
    df_1m = None
    chain_df = None

    if st.session_state.get("c5m") is not None:
        try:
            df_5m = parse_candles_csv(st.session_state.get("c5m"))
        except Exception:
            df_5m = None

    if st.session_state.get("c1m") is not None:
        try:
            df_1m = parse_candles_csv(st.session_state.get("c1m"))
        except Exception:
            df_1m = None

    if st.session_state.get("chainfile") is not None:
        try:
            chain_df = parse_option_chain_csv(st.session_state.get("chainfile"))
        except Exception:
            chain_df = None
    elif st.session_state.get("chainpaste", "").strip():
        try:
            chain_df = parse_option_chain_csv(st.session_state["chainpaste"])
        except Exception:
            chain_df = None

    action, reason, level, trend, support, resistance, pcr = recommendation_engine(
        df_5m=df_5m,
        df_1m=df_1m,
        chain_df=chain_df,
        pcr_low=pcr_low,
        pcr_high=pcr_high,
        level_lookback=level_lookback
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Trend", trend)
    c2.metric("Support", f"{support:,.0f}" if support else "—")
    c3.metric("Resistance", f"{resistance:,.0f}" if resistance else "—")
    c4.metric("PCR", f"{pcr:.2f}" if np.isfinite(pcr) else "—")

    st.markdown("### Recommendation")
    if action == "BUY_CALL":
        st.success(f"✅ BUY CALL (CE)\n\n**Reason:** {reason}")
    elif action == "BUY_PUT":
        st.success(f"✅ BUY PUT (PE)\n\n**Reason:** {reason}")
    else:
        st.info(f"⏸️ NO TRADE\n\n**Reason:** {reason}")

    st.markdown("### Premium SL/Target Suggestions")
    if action == "BUY_CALL" and ce_ltp > 0:
        st.write(f"CE Entry≈₹{ce_ltp:.2f} | SL≈₹{ce_ltp*(1-sl_pct):.2f} | Target≈₹{ce_ltp*(1+tgt_pct):.2f}")
    if action == "BUY_PUT" and pe_ltp > 0:
        st.write(f"PE Entry≈₹{pe_ltp:.2f} | SL≈₹{pe_ltp*(1-sl_pct):.2f} | Target≈₹{pe_ltp*(1+tgt_pct):.2f}")

    now_ts = time.time()
    should_popup = (
        action in ["BUY_CALL", "BUY_PUT"]
        and action != st.session_state.last_action
        and (now_ts - st.session_state.last_popup_ts) >= cooldown_sec
    )

    if should_popup:
        st.session_state.last_action = action
        st.session_state.last_popup_ts = now_ts
        if popup_style == "Toast (recommended)":
            st.toast(f"✅ {action}\n{reason}", icon="✅")
        else:
            js_alert(f"{action} | {reason}")

    st.caption("Popup triggers only when recommendation changes to BUY_CALL/BUY_PUT (with cooldown).")

if auto_refresh:
    time.sleep(refresh_sec)
    st.rerun()
