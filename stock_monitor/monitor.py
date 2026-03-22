#!/usr/bin/env python3
"""
移動平均線 上昇配列モニター
- MA5(1週) > MA25(1ヶ月) > MA75(3ヶ月) の上昇配列を監視
- 状態変化時にmacOS通知 + ログ記録
"""

import json
import os
import subprocess
from datetime import datetime

import pandas as pd
import yfinance as yf

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
LOG_FILE   = os.path.join(BASE_DIR, "monitor.log")

# 監視銘柄
TICKERS = ["TSLA"]

# 移動平均の期間（営業日）
MA_SHORT = 5   # 約1週間
MA_MID   = 25  # 約1ヶ月
MA_LONG  = 75  # 約3ヶ月


# ──────────────────────────────────────────
# データ取得・計算
# ──────────────────────────────────────────

def fetch(ticker: str) -> pd.DataFrame:
    df = yf.download(ticker, period="6mo", interval="1d",
                     auto_adjust=True, progress=False)
    df = df.dropna()
    if len(df) < MA_LONG + 2:
        raise ValueError(f"データ不足: {len(df)} 行")
    return df


def calc_status(df: pd.DataFrame) -> dict:
    df = df.copy()
    df["ma_short"] = df["Close"].rolling(MA_SHORT).mean()
    df["ma_mid"]   = df["Close"].rolling(MA_MID).mean()
    df["ma_long"]  = df["Close"].rolling(MA_LONG).mean()

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    close      = float(latest["Close"].iloc[0]) if hasattr(latest["Close"], "iloc") else float(latest["Close"])
    open_      = float(latest["Open"].iloc[0])  if hasattr(latest["Open"],  "iloc") else float(latest["Open"])
    prev_close = float(prev["Close"].iloc[0])   if hasattr(prev["Close"],   "iloc") else float(prev["Close"])
    ma_s       = float(latest["ma_short"])
    ma_m       = float(latest["ma_mid"])
    ma_l       = float(latest["ma_long"])

    is_green = close > open_
    aligned  = ma_s > ma_m > ma_l

    return {
        "date":       df.index[-1].strftime("%Y-%m-%d"),
        "close":      round(close, 2),
        "open":       round(open_, 2),
        "prev_close": round(prev_close, 2),
        "change_pct": round((close - prev_close) / prev_close * 100, 2),
        "ma_short":   round(ma_s, 2),
        "ma_mid":     round(ma_m, 2),
        "ma_long":    round(ma_l, 2),
        "is_green":   is_green,
        "aligned":    aligned,
    }


# ──────────────────────────────────────────
# 状態の永続化
# ──────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────
# 通知・ログ
# ──────────────────────────────────────────

def notify(title: str, message: str):
    """macOS 通知センターに表示"""
    script = f'display notification "{message}" with title "{title}" sound name "default"'
    subprocess.run(["osascript", "-e", script], check=False)


def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ──────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────

def check_ticker(ticker: str, prev_state: dict) -> dict:
    df     = fetch(ticker)
    status = calc_status(df)

    candle_icon = "🟢 陽線" if status["is_green"] else "🔴 陰線"
    align_icon  = "↑↑↑ 上昇配列" if status["aligned"] else "✗ 配列崩れ"

    # 通常の状態ログ（毎回出力）
    log(
        f"{ticker} [{status['date']}] "
        f"終値 ${status['close']} ({status['change_pct']:+.2f}%)  "
        f"{candle_icon}  {align_icon}  "
        f"MA5={status['ma_short']}  MA25={status['ma_mid']}  MA75={status['ma_long']}"
    )

    # 状態変化の検知
    prev_aligned = prev_state.get("aligned")  # None = 初回

    if prev_aligned is None:
        log(f"  → {ticker}: 初回記録（現在の状態を保存）")

    elif prev_aligned is True and not status["aligned"]:
        msg = "上昇配列が崩れました ⚠️"
        log(f"  → [{ticker}] {msg}")
        notify(f"{ticker} アラート", msg)

    elif prev_aligned is False and status["aligned"]:
        msg = "上昇配列に戻りました ✅"
        log(f"  → [{ticker}] {msg}")
        notify(f"{ticker} 回復", msg)

    else:
        state_label = "上昇配列継続中" if status["aligned"] else "配列崩れ継続中"
        log(f"  → 状態変化なし（{state_label}）")

    return {
        "date":    status["date"],
        "aligned": status["aligned"],
        "close":   status["close"],
    }


def run():
    log("=" * 60)
    log(f"チェック開始  対象: {', '.join(TICKERS)}")

    state = load_state()

    for ticker in TICKERS:
        try:
            state[ticker] = check_ticker(ticker, state.get(ticker, {}))
        except Exception as e:
            log(f"ERROR {ticker}: {e}")

    save_state(state)
    log("チェック完了")
    log("=" * 60)


if __name__ == "__main__":
    run()
