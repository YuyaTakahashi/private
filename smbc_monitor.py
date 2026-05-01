#!/usr/bin/env python3
"""SMBC FX Market Report - 自信指数モニター（GitHub Actions版）
CI = ブル% - ベア%。|CI| >= 35% → エントリー通知、< 35% → 日次サマリー通知
"""
import json, urllib.request, os, sys, datetime, tempfile, re

PDF_URL = "https://www.smbc.co.jp/market/pdf/comment.pdf"
THRESHOLD = 35


def download_pdf(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        with open(dest, "wb") as f:
            f.write(r.read())


def pdf_page_to_png(pdf_path: str, page_num: int, out_png: str, dpi: int = 200) -> None:
    import fitz
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    pix.save(out_png)
    print(f"PNG OK: {pix.width}x{pix.height}")


def extract_bull_bear(png_path: str) -> dict:
    import google.generativeai as genai
    from PIL import Image

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-1.5-flash")
    img = Image.open(png_path)
    prompt = (
        "この画像はSMBC FXマーケットレポートのページです。"
        "「5.ディーラーの予想分布」セクションの「ドル円・ブルベアイメージ」という横棒グラフを見てください。"
        "最新（右側または下側）のグラフについて、ブル（青）・ベア（赤）・ニュートラル（白/グレー）の割合（%）を読み取ってください。"
        "必ずJSON形式のみで回答してください。例: {\"bull\": 40, \"bear\": 20, \"neutral\": 40}"
        "数値が読み取れない場合は {\"bull\": null, \"bear\": null, \"neutral\": null} と返してください。"
    )
    response = model.generate_content([prompt, img])
    text = response.text.strip()
    m = re.search(r'\{[^}]+\}', text)
    if not m:
        raise ValueError(f"JSONが見つかりません: {text}")
    return json.loads(m.group())


def send_line(message: str) -> None:
    token = os.environ["LINE_TOKEN"]
    uid = os.environ["LINE_USER_ID"]
    body = json.dumps({"to": uid, "messages": [{"type": "text", "text": message}]}).encode()
    req = urllib.request.Request(
        "https://api.line.me/v2/bot/message/push",
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    res = urllib.request.urlopen(req, timeout=10)
    print(f"LINE OK: {res.status}")


def main() -> None:
    today = datetime.date.today().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "smbc.pdf")
        png_path = os.path.join(tmpdir, "page2.png")

        print("PDFダウンロード中...")
        download_pdf(PDF_URL, pdf_path)

        print("PNG変換中...")
        pdf_page_to_png(pdf_path, page_num=2, out_png=png_path)

        print("チャート解析中...")
        values = extract_bull_bear(png_path)

    bull = values.get("bull")
    bear = values.get("bear")
    neutral = values.get("neutral")

    if bull is None or bear is None:
        print("ERROR: 数値を読み取れませんでした", file=sys.stderr)
        sys.exit(1)

    ci = bull - bear
    print(f"bull={bull}% bear={bear}% neutral={neutral}% CI={ci:+}%")

    if abs(ci) >= THRESHOLD:
        direction = "BULL long（円安）" if ci > 0 else "BEAR short（円高）"
        icon = "🟢" if ci > 0 else "🔴"
        msg = (
            f"{icon} 【ミラトレ】{direction}\n"
            f"ブル{bull}% / ベア{bear}% → CI={ci:+}%\n"
            f"エントリー条件成立"
        )
    else:
        msg = (
            f"[miratrade] {today} daily\n"
            f"bull {bull}% / bear {bear}% -> CI={ci:+}%\n"
            f"no entry (+-{THRESHOLD}%)"
        )

    send_line(msg)


if __name__ == "__main__":
    main()
