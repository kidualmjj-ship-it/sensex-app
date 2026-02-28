# SENSEX Call/Put Signal App (Manual Trading)

A lightweight **Streamlit** dashboard that helps you decide **BUY CALL / BUY PUT** for **SENSEX options**, based on:

- **Trend + intraday levels** from uploaded **5m candles**
- **Break + Retest trigger** from uploaded **1m candles**
- **Option Chain analytics** from uploaded/pasted CSV (**OI + PCR + OI walls**)
- **Popup alerts** when the recommendation switches to **BUY_CALL / BUY_PUT**
- Simple **index-only backtest** on uploaded candles for sanity-checking parameters

> This app does **NOT** place orders. You trade manually.

---

## Features

### 📈 Live Monitor
- Manual input: SENSEX spot, selected CE/PE premium
- Upload 5m + 1m candle CSVs
- Shows premium-based SL/Target suggestions

### ⛓️ Option Chain
- Upload or paste CSV
- Computes PCR, max OI strikes, strike picker (ATM / 1-step ITM)

### 🧪 Backtest
- Upload candles CSV (1m or 5m)
- Runs a simple breakout backtest (index-only)
- Outputs win rate and expectancy in R-multiples

### 🚨 Signal Panel
- Consolidated recommendation: BUY_CALL / BUY_PUT / NO_TRADE
- Popup alert (Toast or Browser Alert) when signal appears

---

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

---

## Input CSV formats

### Candles CSV (1m / 5m)
Required columns (case-insensitive):
- `open`, `high`, `low`, `close`

Optional:
- `time` / `timestamp`
- `volume`

Example header:
```csv
time,open,high,low,close,volume
```

### Option Chain CSV
Required columns:
- `strike`
- `call_oi` (or `ce_oi`)
- `put_oi` (or `pe_oi`)

Optional:
- `call_oi_chg`, `put_oi_chg`
- `call_ltp`, `put_ltp`

Example header:
```csv
strike,call_oi,put_oi,call_oi_chg,put_oi_chg,call_ltp,put_ltp
```

---

## Disclaimer

This project is for **education and decision-support** only. Markets are risky. Use proper risk management.

---

## License

MIT
