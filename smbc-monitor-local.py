#!/usr/bin/env python3
"""
SMBC FXマーケットレポート 自信指数モニター（ローカル実行版 / cron 平日8:45）

解析は smbc_monitor.analyze_bar に一本化している（PDFのベクター図形から直接読む）。
通知先はLINE、失敗時はメールにフォールバックする。
"""
from __future__ import annotations

import json, os, datetime, tempfile, urllib.request, smtplib, sys
from pathlib import Path
from email.mime.text import MIMEText

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smbc_monitor import PDF_URL, THRESHOLD, analyze_bar, download_pdf

CONFIG_PATH = Path(__file__).parent / "stock_monitor" / "config.json"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


# ── LINE通知 ──────────────────────────────────────────────────────────
def send_line(message: str, config: dict) -> None:
    token = config.get("line_token") or os.environ.get("LINE_TOKEN")
    user_id = config.get("line_user_id") or os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        raise RuntimeError("LINE設定なし（line_token / line_user_id）")
    body = json.dumps({"to": user_id, "messages": [{"type": "text", "text": message}]}).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=body, headers=headers, method="POST"
    )
    urllib.request.urlopen(req, timeout=10)
    print("LINE送信完了")


# ── メール通知 ────────────────────────────────────────────────────────
def send_email(subject: str, body: str, config: dict) -> None:
    from_addr = config["from_address"]
    to_list = config["to_address"] if isinstance(config["to_address"], list) else [config["to_address"]]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_list)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(from_addr, config["app_password"])
        smtp.sendmail(from_addr, to_list, msg.as_string())
    print("メール送信完了:", subject)


def notify(subject: str, message: str, config: dict) -> None:
    """LINEを試し、失敗したらメールに落とす"""
    try:
        send_line(message, config)
    except Exception as e:
        print("LINE失敗:", e)
        send_email(subject, message, config)


# ── メイン ────────────────────────────────────────────────────────────
def main() -> None:
    config = load_config()
    today = datetime.date.today().strftime("%Y-%m-%d")

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "smbc.pdf")
        print("PDFダウンロード中...")
        download_pdf(PDF_URL, pdf_path)
        print("チャート解析中...")
        try:
            bull, bear, neutral = analyze_bar(pdf_path)
        except Exception as e:
            print("解析失敗:", e)
            notify(
                f"[SMBC ミラトレ] {today} 解析失敗",
                f"⚠️ 解析に失敗しました\n{e}\n{PDF_URL}",
                config,
            )
            raise

    ci = bull - bear
    print(f"bull={bull}% bear={bear}% neutral={neutral}% CI={ci:+}%")

    if abs(ci) >= THRESHOLD:
        direction = "BULL ロング（円安）" if ci > 0 else "BEAR ショート（円高）"
        icon = "🟢" if ci > 0 else "🔴"
        msg = (
            f"{icon} 【ミラトレ】{direction}\n"
            f"ブル{bull}% / ベア{bear}% → CI={ci:+}%\n"
            f"エントリー条件成立"
        )
        notify(f"[SMBC ミラトレ] {today} CI={ci:+}% エントリー条件成立", msg, config)
    else:
        msg = (
            f"[miratrade] {today} daily\n"
            f"bull {bull}% / bear {bear}% / neutral {neutral}% -> CI={ci:+}%\n"
            f"{PDF_URL}"
        )
        notify(f"[SMBC ミラトレ] {today} daily CI={ci:+}%", msg, config)


if __name__ == "__main__":
    main()
