#!/usr/bin/env python3
"""SMBC FX Market Report - 自信指数モニター（GitHub Actions版）
CI = ブル% - ベア%。|CI| >= 35% → エントリー通知、< 35% → 日次サマリー通知
"""
import json, urllib.request, os, sys, datetime, tempfile, time

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
    """ピクセル色解析でブル/ベア/ニュートラル%を返す。
    SMBCの凡例: 赤=ブル、青=ベア、白=ニュートラル。
    """
    from PIL import Image
    img = Image.open(png_path).convert("RGB")
    w, h = img.size

    def is_dark(r, g, b, thr=120):
        avg = (r + g + b) // 3
        if avg >= thr:
            return False
        return abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30

    # 「5.ディーラーの予想分布」のドル円バーは縦65〜71%、左半分にある
    y_band = (int(h * 0.65), int(h * 0.71))
    x_band = (30, int(w * 0.50))
    band_w = x_band[1] - x_band[0]

    # バーの上下枠（細い水平黒線）を検出
    horiz_borders = [
        y for y in range(*y_band)
        if sum(1 for x in range(*x_band) if is_dark(*img.getpixel((x, y)))) >= band_w * 0.6
    ]
    hgroups = []
    if horiz_borders:
        cur = [horiz_borders[0]]
        for y in horiz_borders[1:]:
            if y - cur[-1] <= 2:
                cur.append(y)
            else:
                hgroups.append((cur[0], cur[-1]))
                cur = [y]
        hgroups.append((cur[0], cur[-1]))
    thin = [g for g in hgroups if g[1] - g[0] <= 3]
    top_border = bot_border = None
    for i, g1 in enumerate(thin):
        for g2 in thin[i + 1:]:
            if 20 <= g2[0] - g1[1] <= 60:
                top_border, bot_border = g1, g2
                break
        if top_border:
            break
    if top_border is None:
        return 0, 0, 100

    # 上枠行の最長ダークラン = バーの左右枠
    y = top_border[0]
    dark_xs = [x for x in range(*x_band) if is_dark(*img.getpixel((x, y)))]
    runs = []
    if dark_xs:
        cur = [dark_xs[0]]
        for x in dark_xs[1:]:
            if x - cur[-1] <= 2:
                cur.append(x)
            else:
                runs.append((cur[0], cur[-1]))
                cur = [x]
        runs.append((cur[0], cur[-1]))
    if not runs:
        return 0, 0, 100
    longest = max(runs, key=lambda r: r[1] - r[0])
    inner_x0, inner_x1 = longest[0] + 1, longest[1] - 1
    inner_y0, inner_y1 = top_border[1] + 1, bot_border[0] - 1

    inner = img.crop((inner_x0, inner_y0, inner_x1, inner_y1))
    iw, ih = inner.size
    bull_px = bear_px = neutral_px = 0
    for x in range(iw):
        for yy in range(ih):
            r, g, b = inner.getpixel((x, yy))
            if b > 130 and b > r + 30:
                bear_px += 1   # 青 = ベア
            elif r > 130 and r > b + 30 and r > g - 10:
                bull_px += 1   # 赤 = ブル
            elif r > 200 and g > 200 and b > 200:
                neutral_px += 1

    total = bull_px + bear_px + neutral_px
    if total == 0:
        return 0, 0, 100
    bull_pct = round(100 * bull_px / total)
    bear_pct = round(100 * bear_px / total)
    return bull_pct, bear_pct, max(0, 100 - bull_pct - bear_pct)


def build_flex(text: str, pdf_url: str) -> dict:
    return {
        "type": "flex",
        "altText": text[:400],
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [{"type": "text", "text": text, "wrap": True}],
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "action": {"type": "uri", "label": "PDFを開く", "uri": pdf_url},
                        "style": "primary",
                    }
                ],
            },
        },
    }


def send_line(message: dict, retries: int = 3, delay: float = 5.0) -> None:
    token = os.environ["LINE_TOKEN"]
    uid = os.environ["LINE_USER_ID"]
    body = json.dumps({"to": uid, "messages": [message]}).encode()
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                "https://api.line.me/v2/bot/message/push",
                data=body,
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST",
            )
            res = urllib.request.urlopen(req, timeout=15)
            print(f"LINE OK: {res.status}")
            return
        except Exception as e:
            last_err = e
            print(f"LINE attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(delay)
    raise RuntimeError(f"LINE send failed after {retries} attempts") from last_err


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
        if ci > 0:
            label, icon, action = "BULL", "🟢", "USD/JPY 買い（ドル買い・円売り）"
        else:
            label, icon, action = "BEAR", "🔴", "USD/JPY 売り（ドル売り・円買い）"
        text = (
            f"{icon} 【ミラトレ】{label} エントリー成立\n"
            f"ブル{bull}% / ベア{bear}% → CI={ci:+}%\n"
            f"👉 {action}"
        )
    else:
        text = (
            f"[miratrade] {today} daily\n"
            f"bull {bull}% / bear {bear}% -> CI={ci:+}%\n"
            f"no entry (+-{THRESHOLD}%)"
        )

    send_line(build_flex(text, PDF_URL))


if __name__ == "__main__":
    main()
