#!/usr/bin/env python3
"""SMBC FX Market Report - 自信指数モニター（GitHub Actions版）
CI = ブル% - ベア%。|CI| >= 35% → エントリー通知、< 35% → 日次サマリー通知

解析はPDFのベクター図形から「5.ディーラーの予想分布」のドル円バーを直接取り出す。
各セグメントの色はレンダリング結果から判定する（凡例: 青=ベア / 白=ニュートラル / 赤=ブル）。
"""
from __future__ import annotations  # Python 3.9 でも `str | None` を書けるようにする

import json, urllib.request, os, datetime, tempfile, time

PDF_URL = "https://www.smbc.co.jp/market/pdf/comment.pdf"
THRESHOLD = 35
SECTION_KEYWORD = "ディーラーの予想分布"
RENDER_SCALE = 200 / 72  # 200dpi相当


def download_pdf(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        with open(dest, "wb") as f:
            f.write(r.read())


def _classify(r: int, g: int, b: int) -> str | None:
    if b > 130 and b > r + 30 and b > g + 30:
        return "bear"
    if r > 130 and r > b + 30 and r > g + 30:
        return "bull"
    if r > 200 and g > 200 and b > 200:
        return "neutral"
    return None


def _segment_color(pix, rect, scale: float) -> str:
    """セグメント矩形に対応する描画領域を走査し、支配的な色を返す。
    バーは網点パターンで塗られているので1点ではなく面でサンプリングする。
    """
    x0, x1 = int(rect.x0 * scale) + 2, min(int(rect.x1 * scale) - 2, pix.width)
    y0, y1 = int(rect.y0 * scale) + 2, min(int(rect.y1 * scale) - 2, pix.height)
    if x1 <= x0 or y1 <= y0:
        return "neutral"
    tally = {"bear": 0, "bull": 0, "neutral": 0}
    step = max(1, (x1 - x0) // 40)
    for x in range(x0, x1, step):
        for y in range(y0, y1):
            c = _classify(*pix.pixel(x, y)[:3])
            if c:
                tally[c] += 1
    if tally["bear"] == tally["bull"] == 0:
        return "neutral"
    return max(tally, key=tally.get)


def _dedupe(rects, tol: float = 0.4):
    """このPDFは同じ内容を二重に描画するため、ほぼ同一の矩形は1つに畳む"""
    out = []
    for r in rects:
        if any(
            abs(k.x0 - r.x0) < tol and abs(k.y0 - r.y0) < tol
            and abs(k.x1 - r.x1) < tol and abs(k.y1 - r.y1) < tol
            for k in out
        ):
            continue
        out.append(r)
    return out


def analyze_bar(pdf_path: str) -> tuple[int, int, int]:
    """ドル円バーの (bull%, bear%, neutral%) を返す。
    検出できなかった場合は例外を投げる（黙って0,0,100を返すと故障が見えなくなるため）。
    """
    import fitz

    doc = fitz.open(pdf_path)
    page, hits = None, []
    for p in doc:
        found = p.search_for(SECTION_KEYWORD)
        if found:
            page, hits = p, found
            break
    if page is None:
        raise ValueError(f"「{SECTION_KEYWORD}」の見出しが見つかりません")

    y_top = hits[0].y1
    y_bot = y_top + 80

    cands = _dedupe([
        d["rect"] for d in page.get_drawings()
        if y_top < d["rect"].y0 < y_bot
        and 5 <= d["rect"].height <= 30 and d["rect"].width >= 2
    ])
    cands.sort(key=lambda r: (round(r.y0, 1), r.x0))

    # 同じ高さで水平に連続する矩形をひとかたまり（＝1本のバー）にまとめる
    runs = []
    for r in cands:
        if runs:
            p = runs[-1][-1]
            if (abs(p.y0 - r.y0) < 0.5 and abs(p.y1 - r.y1) < 0.5
                    and abs(p.x1 - r.x0) < 1.0):
                runs[-1].append(r)
                continue
        runs.append([r])

    pix = page.get_pixmap(matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE))

    bars = []
    for run in runs:
        total = sum(s.width for s in run)
        if total <= 50:
            continue
        colors = [_segment_color(pix, s, RENDER_SCALE) for s in run]
        # 青か赤を含むものだけが実際のバー（白背景の枠を除外する）
        if any(c in ("bear", "bull") for c in colors):
            bars.append((run, colors, total))

    if not bars:
        raise ValueError("ブル/ベアのバーを検出できませんでした（PDFのレイアウト変更の可能性）")

    bars.sort(key=lambda t: t[0][0].x0)
    run, colors, total = bars[0]  # 左＝ドル円、右＝ユーロ円

    pct = {"bull": 0.0, "bear": 0.0, "neutral": 0.0}
    for seg, c in zip(run, colors):
        pct[c] += 100 * seg.width / total

    bull, bear = round(pct["bull"]), round(pct["bear"])
    detail = " / ".join(f"{c}:{s.width:.1f}pt" for s, c in zip(run, colors))
    print(f"bar x={run[0].x0:.1f}-{run[-1].x1:.1f} total={total:.1f}pt  {detail}")
    return bull, bear, max(0, 100 - bull - bear)


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

        print("PDFダウンロード中...")
        download_pdf(PDF_URL, pdf_path)

        print("チャート解析中...")
        try:
            bull, bear, neutral = analyze_bar(pdf_path)
        except Exception as e:
            print(f"解析失敗: {e}")
            send_line(build_flex(
                f"⚠️ 【ミラトレ】{today} 解析失敗\n{e}\nPDFを直接確認してください。", PDF_URL))
            raise

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
            f"bull {bull}% / bear {bear}% / neutral {neutral}% -> CI={ci:+}%\n"
            f"no entry (+-{THRESHOLD}%)"
        )

    send_line(build_flex(text, PDF_URL))


if __name__ == "__main__":
    main()
