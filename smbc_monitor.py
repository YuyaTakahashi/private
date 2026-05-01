#!/usr/bin/env python3
"""SMBC FX Market Report - 自信指数モニター（GitHub Actions版）
CI = ブル% - ベア%。|CI| >= 35% → エントリー通知、< 35% → 日次サマリー通知
"""
import json, urllib.request, os, sys, datetime, tempfile

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


def analyze_bar(png_path: str) -> tuple[int, int, int]:
    """ピクセル色解析でブル/ベア/ニュートラル%を返す"""
    from PIL import Image
    img = Image.open(png_path).convert("RGB")
    w, h = img.size

    # ページ縦65〜70%付近にブルベアバーチャートがある（200dpi=2339px時）
    bar_top = int(h * 0.665)
    bar_bot = int(h * 0.695)
    bar_right = int(w * 0.52)  # 左半分がドル円

    crop = img.crop((30, bar_top, bar_right, bar_bot))
    cw, ch = crop.size

    # バー枠の内側を自動検出
    mid_y = ch // 2
    bar_x_start = bar_x_end = None
    for x in range(cw):
        r, g, b = crop.getpixel((x, mid_y))
        brightness = (r + g + b) // 3
        if brightness < 200 and bar_x_start is None:
            bar_x_start = x + 1
        if bar_x_start and brightness < 200 and x > bar_x_start + 10:
            bar_x_end = x - 1

    if bar_x_start is None or bar_x_end is None or bar_x_end <= bar_x_start:
        bar_x_start, bar_x_end = int(cw * 0.05), int(cw * 0.95)

    bull_px = bear_px = neutral_px = 0
    bar_crop = crop.crop((bar_x_start, int(ch * 0.2), bar_x_end, int(ch * 0.8)))
    bc_w, bc_h = bar_crop.size

    for x in range(bc_w):
        for y in range(bc_h):
            r, g, b = bar_crop.getpixel((x, y))
            if b > 130 and b > r + 30:
                bull_px += 1
            elif r > 130 and r > b + 30 and r > g - 10:
                bear_px += 1
            elif r > 200 and g > 200 and b > 200:
                neutral_px += 1

    total = bull_px + bear_px + neutral_px
    if total == 0:
        return 0, 0, 100

    bull_pct = round(100 * bull_px / total)
    bear_pct = round(100 * bear_px / total)
    return bull_pct, bear_pct, max(0, 100 - bull_pct - bear_pct)


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
        bull, bear, neutral = analyze_bar(png_path)

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
