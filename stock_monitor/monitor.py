#!/usr/bin/env python3
"""
移動平均線 上昇配列モニター
- MA5(1週) > MA25(1ヶ月) > MA75(3ヶ月) の上昇配列を監視
- 崩れ具合を3段階で評価
- 状態変化時にメール通知 + ログ記録
"""

import json
import os
import smtplib
import urllib.request
import urllib.parse
from datetime import datetime
from email.mime.text import MIMEText

import pandas as pd
import yfinance as yf

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
STATE_FILE  = os.path.join(BASE_DIR, "state.json")
LOG_FILE    = os.path.join(BASE_DIR, "monitor.log")
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

# 優先度定義
PRIORITY_NORMAL  = 0  # 🟢 上昇配列
PRIORITY_MILD    = 1  # 🟡 軽度：MA5 < MA25、MA25 > MA75（1週が1ヶ月を割れ）
PRIORITY_SEVERE  = 2  # 🔴 重度：MA25 < MA75（1ヶ月が3ヶ月を割れ）

PRIORITY_LABEL = {
    PRIORITY_NORMAL: "🟢 上昇配列",
    PRIORITY_MILD:   "🟡 軽度崩れ（1週 < 1ヶ月）",
    PRIORITY_SEVERE: "🔴 重度崩れ（1ヶ月 < 3ヶ月）",
}


# ──────────────────────────────────────────
# 設定読み込み
# ──────────────────────────────────────────

def load_config() -> dict:
    # GitHub Actions では環境変数から読む
    if os.environ.get("GMAIL_FROM"):
        to_raw = os.environ.get("GMAIL_TO", "")
        to_addr = [a.strip() for a in to_raw.split(",")] if "," in to_raw else to_raw
        return {
            "from_address": os.environ["GMAIL_FROM"],
            "to_address":   to_addr,
            "app_password": os.environ["GMAIL_APP_PASSWORD"],
        }
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
    # 新しいyfinanceはMultiIndexカラムを返す場合があるのでフラット化
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
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

    # 優先度判定
    if ma_s > ma_m and ma_m > ma_l:
        priority = PRIORITY_NORMAL
    elif ma_m < ma_l:
        priority = PRIORITY_SEVERE   # 1ヶ月 < 3ヶ月（より深刻）
    else:
        priority = PRIORITY_MILD     # 1週 < 1ヶ月のみ

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
        "aligned":    priority == PRIORITY_NORMAL,
        "priority":   priority,
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
# LINE Notify
# ──────────────────────────────────────────

def send_line(message: str, config: dict):
    token   = config.get("line_token") or os.environ.get("LINE_TOKEN")
    user_id = config.get("line_user_id") or os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        return
    body    = json.dumps({
        "to": user_id,
        "messages": [{"type": "text", "text": message}]
    }).encode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    req = urllib.request.Request("https://api.line.me/v2/bot/message/push",
                                 data=body, headers=headers, method="POST")
    urllib.request.urlopen(req)


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

def format_row(ticker: str, s: dict) -> str:
    candle = "陽線" if s["is_green"] else "陰線"
    return (
        f"  {ticker:<8}  終値 ${s['close']:>8.2f} ({s['change_pct']:+.2f}%)"
        f"  {candle}  MA5={s['ma_short']}  MA25={s['ma_mid']}  MA75={s['ma_long']}"
    )


def check_ticker(ticker: str, prev_state: dict, alerts: list) -> dict:
    df     = fetch(ticker)
    status = calc_status(df)

    candle_icon   = "陽線" if status["is_green"] else "陰線"
    priority_label = PRIORITY_LABEL[status["priority"]]

    log(
        f"{ticker} [{status['date']}] "
        f"終値 ${status['close']} ({status['change_pct']:+.2f}%)  "
        f"{candle_icon}  {priority_label}  "
        f"MA5={status['ma_short']}  MA25={status['ma_mid']}  MA75={status['ma_long']}"
    )

    prev_priority = prev_state.get("priority")  # None = 初回

    if prev_priority is None:
        log(f"  → {ticker}: 初回記録")
    elif prev_priority != status["priority"]:
        label_from = PRIORITY_LABEL[prev_priority]
        label_to   = PRIORITY_LABEL[status["priority"]]
        log(f"  → {ticker}: {label_from} → {label_to}")
        alerts.append((ticker, prev_priority, status["priority"], status))
    else:
        log(f"  → 状態変化なし（{priority_label}）")

    return {
        "date":       status["date"],
        "aligned":    status["aligned"],
        "priority":   status["priority"],
        "close":      status["close"],
        "change_pct": status["change_pct"],
        "is_green":   status["is_green"],
    }


def run_test_notify(config: dict):
    """メール（全銘柄実データ）＋LINE（サンプル状態変化）のテスト送信"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # メール: 全銘柄を実際に取得して送信
    groups = {p: [] for p in (PRIORITY_NORMAL, PRIORITY_MILD, PRIORITY_SEVERE)}
    for ticker in TICKERS:
        try:
            df = fetch(ticker)
            s  = calc_status(df)
            groups[s["priority"]].append((ticker, s))
        except Exception as e:
            log(f"ERROR {ticker}: {e}")

    mail_lines = [f"【テスト】日次レポート  {now_str}", "（これはテスト送信です）", ""]
    for pri, label in PRIORITY_LABEL.items():
        mail_lines.append(f"{label}  ({len(groups[pri])} 銘柄)")
        for ticker, s in groups[pri]:
            mail_lines.append(format_row(ticker, s))
        mail_lines.append("")
    send_email(f"【株モニター】テスト送信  {now_str}", "\n".join(mail_lines), config)
    log("メール テスト送信完了")

    # LINE: サンプル状態変化
    sample_alerts = [
        ("NVDA", PRIORITY_SEVERE, PRIORITY_MILD,  {"close": 172.70, "change_pct": +3.21}),
        ("TSLA", PRIORITY_MILD,   PRIORITY_NORMAL, {"close": 370.00, "change_pct": +2.10}),
    ]
    line_lines = ["【株アラート】テスト送信（サンプル）"]
    for ticker, p_from, p_to, s in sample_alerts:
        line_lines.append(
            f"\n{ticker}  ${s['close']} ({s['change_pct']:+.2f}%)"
            f"\n{PRIORITY_LABEL[p_from]} → {PRIORITY_LABEL[p_to]}"
        )
    send_line("\n".join(line_lines), config)
    log("LINE テスト送信完了")


def run():
    config = load_config()

    if os.environ.get("TEST_NOTIFY", "").lower() == "true":
        run_test_notify(config)
        return


    # 同日の2重実行を防ぐ（夏時間・冬時間の2スケジュール対策）
    state = load_state()
    latest_df = yf.download(TICKERS[0], period="5d", interval="1d",
                            auto_adjust=True, progress=False).dropna()
    latest_trading_date = latest_df.index[-1].strftime("%Y-%m-%d")

    if state.get("last_run_date") == latest_trading_date:
        log(f"本日分 ({latest_trading_date}) は処理済み → スキップ")
        return

    log("=" * 60)
    log(f"チェック開始  対象: {len(TICKERS)} 銘柄")

    state  = load_state()
    alerts = []

    for ticker in TICKERS:
        try:
            state[ticker] = check_ticker(ticker, state.get(ticker, {}), alerts)
        except Exception as e:
            log(f"ERROR {ticker}: {e}")

    state["last_run_date"] = latest_trading_date
    save_state(state)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── メール: 毎日送信（全銘柄サマリー + 状態変化）──
    groups = {p: [] for p in (PRIORITY_NORMAL, PRIORITY_MILD, PRIORITY_SEVERE)}
    for ticker in TICKERS:
        s = state.get(ticker)
        if s:
            groups[s["priority"]].append((ticker, s))

    mail_lines = [f"日次レポート  {now_str}", ""]
    for pri, label in PRIORITY_LABEL.items():
        mail_lines.append(f"{label}  ({len(groups[pri])} 銘柄)")
        for ticker, s in groups[pri]:
            candle = "陽線" if s.get("is_green") else "陰線"
            mail_lines.append(
                f"  {ticker:<8}  ${s['close']:>8.2f}  {candle}"
            )
        mail_lines.append("")

    if alerts:
        alerts.sort(key=lambda a: -a[2])
        mail_lines.append("── 本日の状態変化 ──")
        for ticker, p_from, p_to, s in alerts:
            mail_lines.append(f"{PRIORITY_LABEL[p_from]} → {PRIORITY_LABEL[p_to]}")
            mail_lines.append(format_row(ticker, s))
            mail_lines.append("")
        subject = f"【株アラート】{len(alerts)}件の状態変化あり  {now_str}"
    else:
        subject = f"【株モニター】日次レポート  {now_str}"

    send_email(subject, "\n".join(mail_lines), config)
    log(f"メール送信: {subject}")

    # ── LINE: 状態変化時のみ ──
    if alerts:
        line_lines = [f"【株アラート】{len(alerts)}件の状態変化"]
        for ticker, p_from, p_to, s in alerts:
            line_lines.append(
                f"\n{ticker}  ${s['close']} ({s['change_pct']:+.2f}%)"
                f"\n{PRIORITY_LABEL[p_from]} → {PRIORITY_LABEL[p_to]}"
            )
        send_line("\n".join(line_lines), config)
        log("LINE通知送信")
    else:
        log("状態変化なし → LINE送信スキップ")

    log("チェック完了")
    log("=" * 60)


if __name__ == "__main__":
    run()
