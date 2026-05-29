#!/usr/bin/env python3
"""
SMBC FXマーケットレポート 自信指数モニター（ローカル実行版）
ピクセル色分析でブル/ベア比率を読み取り、LINE/メールで通知する。
"""
import json, urllib.request, smtplib, subprocess, os, sys, datetime, tempfile
from pathlib import Path
from email.mime.text import MIMEText
from PIL import Image

# ── 設定 ──────────────────────────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "stock_monitor" / "config.json"
PDF_URL = "https://www.smbc.co.jp/market/pdf/comment.pdf"
THRESHOLD = 35

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

# ── PDF取得 & PNG変換 ─────────────────────────────────────────────────
def fetch_chart_png(tmpdir: str) -> str:
    pdf = os.path.join(tmpdir, "smbc.pdf")
    ppm_prefix = os.path.join(tmpdir, "page")
    png = os.path.join(tmpdir, "chart.png")

    req = urllib.request.Request(PDF_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        with open(pdf, "wb") as f:
            f.write(r.read())

    subprocess.run(
        ["/opt/homebrew/bin/pdftoppm", "-r", "200", "-f", "2", "-l", "2", pdf, ppm_prefix],
        check=True, capture_output=True
    )
    subprocess.run(
        ["/usr/bin/sips", "-s", "format", "png", f"{ppm_prefix}-2.ppm", "--out", png],
        check=True, capture_output=True
    )
    return png

# ── ブル/ベア比率をピクセル分析で読み取る ─────────────────────────────
def analyze_bar(png_path: str) -> tuple[int, int, int]:
    """(bull_pct, bear_pct, neutral_pct) を返す"""
    img = Image.open(png_path).convert("RGB")
    w, h = img.size

    # セクション5（ディーラー予想分布）のドル円バーチャートを切り出す
    # ページの縦65〜70%付近にバーがある（200dpiで2339px高さ時）
    bar_top = int(h * 0.665)
    bar_bot = int(h * 0.695)
    # 左半分がドル円（右半分はユーロ円）
    bar_right = int(w * 0.52)

    crop = img.crop((30, bar_top, bar_right, bar_bot))
    cw, ch = crop.size

    # バーの内側領域を自動検出: 上下中央付近の横ラインを走査
    # バー枠（暗色）を探してその内側だけを分析
    mid_y = ch // 2
    bar_x_start = bar_x_end = None
    for x in range(cw):
        r, g, b = crop.getpixel((x, mid_y))
        brightness = (r + g + b) // 3
        # 枠の外（白い背景）→ 内側の切り替わりポイント
        if brightness < 200 and bar_x_start is None:
            bar_x_start = x + 1
        if bar_x_start and brightness < 200 and x > bar_x_start + 10:
            bar_x_end = x - 1

    if bar_x_start is None or bar_x_end is None or bar_x_end <= bar_x_start:
        # フォールバック: クロップ全体を使う
        bar_x_start, bar_x_end = int(cw * 0.05), int(cw * 0.95)

    # バー内のピクセルを色分類
    bull_px = bear_px = neutral_px = 0
    bar_crop = crop.crop((bar_x_start, int(ch * 0.2), bar_x_end, int(ch * 0.8)))
    bc_w, bc_h = bar_crop.size

    for x in range(bc_w):
        for y in range(bc_h):
            r, g, b = bar_crop.getpixel((x, y))
            # ブル: 青系・水色系
            if b > 130 and b > r + 30:
                bull_px += 1
            # ベア: 赤系・コーラル系
            elif r > 130 and r > b + 30 and r > g - 10:
                bear_px += 1
            # ニュートラル: 白/薄グレー
            elif r > 200 and g > 200 and b > 200:
                neutral_px += 1

    total_bar = bull_px + bear_px + neutral_px
    if total_bar == 0:
        return 0, 0, 100

    bull_pct = round(100 * bull_px / total_bar)
    bear_pct = round(100 * bear_px / total_bar)
    neutral_pct = 100 - bull_pct - bear_pct

    return bull_pct, bear_pct, max(0, neutral_pct)

# ── LINE通知 ──────────────────────────────────────────────────────────
def send_line(message: str, config: dict):
    token = config.get("line_token") or os.environ.get("LINE_TOKEN")
    user_id = config.get("line_user_id") or os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        print("LINE設定なし、スキップ")
        return
    body = json.dumps({"to": user_id, "messages": [{"type": "text", "text": message}]}).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=body, headers=headers, method="POST"
    )
    urllib.request.urlopen(req, timeout=10)
    print("LINE送信完了")

# ── メール通知 ────────────────────────────────────────────────────────
def send_email(subject: str, body: str, config: dict):
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

# ── メイン ────────────────────────────────────────────────────────────
def main():
    config = load_config()
    today = datetime.date.today().strftime("%Y-%m-%d")

    with tempfile.TemporaryDirectory() as tmpdir:
        print("PDFダウンロード中...")
        png_path = fetch_chart_png(tmpdir)
        print("チャート解析中...")
        bull, bear, neutral = analyze_bar(png_path)

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
        try:
            send_line(msg, config)
        except Exception as e:
            print("LINE失敗:", e)
            send_email(
                f"[SMBC ミラトレ] {today} CI={ci:+}% エントリー条件成立（LINE失敗）",
                msg, config
            )
    else:
        msg = (
            f"[miratrade] {today} daily\n"
            f"bull {bull}% / bear {bear}% -> CI={ci:+}%\n"
            f"{PDF_URL}"
        )
        send_line(msg, config)

if __name__ == "__main__":
    main()
