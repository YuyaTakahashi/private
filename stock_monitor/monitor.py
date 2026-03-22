#!/usr/bin/env python3
"""
移動平均線 上昇配列モニター
- MA5(1週) > MA25(1ヶ月) > MA75(3ヶ月) の上昇配列を監視
- 状態変化時にメール通知 + ログ記録
"""

import json
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText

import pandas as pd
import yfinance as yf

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")
LOG_FILE   = os.path.join(BASE_DIR, "monitor.log")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# 監視銘柄（日本株は末尾に .T）
TICKERS = [
    "2760.T",  # 東京エレクトロン デバイス
    "ADI",     # アナログ・デバイシズ
    "AMD",     # アドバンスト・マイクロ
    "AMZN",    # アマゾン
    "ARM",     # アーム・ホールディングス
    "AVGO",    # ブロードコム
    "CEG",     # コンステレーション・エナジー
    "DIOD",    # ダイオーズ
    "GOOG",    # アルファベット クラスC
    "GOOGL",   # アルファベット クラスA
    "HON",     # ハネウェル
    "IBM",     # IBM
    "INFQ",    # インフレクション
    "IRDM",    # イリジウム
    "LMT",     # ロッキード・マーチン
    "MSFT",    # マイクロソフト
    "MU",      # マイクロン
    "NVDA",    # エヌビディア
    "PLTR",    # パランティア
    "QCOM",    # クアルコム
    "RTX",     # RTX
    "SMCI",    # スーパー・マイクロ
    "SSYS",    # ストラタシス
    "TSLA",    # テスラ
    "TSM",     # 台湾セミコンダクター
]

# 移動平均の期間（営業日）
MA_SHORT = 5   # 約1週間
MA_MID   = 25  # 約1ヶ月
MA_LONG  = 75  # 約3ヶ月


# ──────────────────────────────────────────
# 設定読み込み
# ──────────────────────────────────────────

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        raise FileNotFoundError(
            f"config.json が見つかりません。\n"
            f"cp {BASE_DIR}/config.json.example {CONFIG_FILE} して設定してください。"
        )
    with open(CONFIG_FILE) as f:
        return json.load(f)


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

    def to_float(val):
        return float(val.iloc[0]) if hasattr(val, "iloc") else float(val)

    close      = to_float(latest["Close"])
    open_      = to_float(latest["Open"])
    prev_close = to_float(prev["Close"])
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
# メール通知
# ──────────────────────────────────────────

def send_email(subject: str, body: str, config: dict):
    to_list = config["to_address"] if isinstance(config["to_address"], list) else [config["to_address"]]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"]    = config["from_address"]
    msg["To"]      = ", ".join(to_list)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(config["from_address"], config["app_password"])
        smtp.sendmail(config["from_address"], to_list, msg.as_string())


# ──────────────────────────────────────────
# ログ
# ──────────────────────────────────────────

def log(msg: str):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ──────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────

def check_ticker(ticker: str, prev_state: dict, config: dict, alerts: list) -> dict:
    df     = fetch(ticker)
    status = calc_status(df)

    candle_icon = "🟢 陽線" if status["is_green"] else "🔴 陰線"
    align_icon  = "↑↑↑ 上昇配列" if status["aligned"] else "✗ 配列崩れ"

    log(
        f"{ticker} [{status['date']}] "
        f"終値 ${status['close']} ({status['change_pct']:+.2f}%)  "
        f"{candle_icon}  {align_icon}  "
        f"MA5={status['ma_short']}  MA25={status['ma_mid']}  MA75={status['ma_long']}"
    )

    prev_aligned = prev_state.get("aligned")  # None = 初回

    if prev_aligned is None:
        log(f"  → {ticker}: 初回記録（現在の状態を保存）")

    elif prev_aligned is True and not status["aligned"]:
        msg = f"{ticker}: 上昇配列が崩れました ⚠️  終値 ${status['close']} ({status['change_pct']:+.2f}%)"
        log(f"  → {msg}")
        alerts.append(("崩れ", ticker, msg, status))

    elif prev_aligned is False and status["aligned"]:
        msg = f"{ticker}: 上昇配列に戻りました ✅  終値 ${status['close']} ({status['change_pct']:+.2f}%)"
        log(f"  → {msg}")
        alerts.append(("回復", ticker, msg, status))

    else:
        state_label = "上昇配列継続中" if status["aligned"] else "配列崩れ継続中"
        log(f"  → 状態変化なし（{state_label}）")

    return {
        "date":    status["date"],
        "aligned": status["aligned"],
        "close":   status["close"],
    }


def run():
    config = load_config()

    log("=" * 60)
    log(f"チェック開始  対象: {len(TICKERS)} 銘柄")

    state  = load_state()
    alerts = []  # (種別, ticker, msg, status)

    for ticker in TICKERS:
        try:
            state[ticker] = check_ticker(ticker, state.get(ticker, {}), config, alerts)
        except Exception as e:
            log(f"ERROR {ticker}: {e}")

    save_state(state)

    # アラートをまとめてメール送信
    if alerts:
        broke   = [a for a in alerts if a[0] == "崩れ"]
        recover = [a for a in alerts if a[0] == "回復"]

        subject = f"【株アラート】{len(alerts)} 件の状態変化"
        lines = [f"チェック日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]

        if broke:
            lines.append("■ 上昇配列が崩れた銘柄")
            for _, ticker, msg, s in broke:
                lines.append(f"  {ticker}  終値 ${s['close']} ({s['change_pct']:+.2f}%)")
                lines.append(f"    MA5={s['ma_short']}  MA25={s['ma_mid']}  MA75={s['ma_long']}")
            lines.append("")

        if recover:
            lines.append("■ 上昇配列に戻った銘柄")
            for _, ticker, msg, s in recover:
                lines.append(f"  {ticker}  終値 ${s['close']} ({s['change_pct']:+.2f}%)")
                lines.append(f"    MA5={s['ma_short']}  MA25={s['ma_mid']}  MA75={s['ma_long']}")

        body = "\n".join(lines)
        send_email(subject, body, config)
        log(f"メール送信: {subject}")
    else:
        log("状態変化なし → メール送信スキップ")

    log("チェック完了")
    log("=" * 60)


if __name__ == "__main__":
    run()
