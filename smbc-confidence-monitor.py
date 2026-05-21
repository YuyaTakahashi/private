#!/usr/bin/env python3
"""
SMBC FXマーケットレポートからドル円の自信指数（コンフィデンスインデックス）を取得する。
CI = ブル% - ベア%
|CI| >= 35% のとき、エントリー方向とともに結果を出力する。

出力（JSON）:
{
  "bull_pct": 40,
  "bear_pct": 10,
  "neutral_pct": 50,
  "confidence_index": 30,
  "direction": "BULL",
  "threshold_met": false,
  "date": "2026-04-25"
}
"""
import subprocess
import tempfile
import os
import sys
import json
import base64
import urllib.request
from datetime import date

PDF_URL = "https://www.smbc.co.jp/market/pdf/comment.pdf"
THRESHOLD = 35


def download_pdf(url: str, dest: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        with open(dest, "wb") as f:
            f.write(resp.read())


def pdf_page_to_png(pdf_path: str, page: int, out_png: str, dpi: int = 200) -> None:
    """pdftoppm + sips でPDFの指定ページをPNGに変換する。"""
    ppm_prefix = out_png.replace(".png", "")
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-f", str(page), "-l", str(page), pdf_path, ppm_prefix],
        check=True, capture_output=True
    )
    ppm_file = f"{ppm_prefix}-{page}.ppm"
    subprocess.run(
        ["sips", "-s", "format", "png", ppm_file, "--out", out_png],
        check=True, capture_output=True
    )
    os.remove(ppm_file)


def extract_bull_bear_from_image(image_path: str) -> dict:
    """Claude vision API でブル/ベア/ニュートラル%を読み取る。"""
    import anthropic

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "この画像はSMBC FXマーケットレポートのページです。"
                            "「5.ディーラーの予想分布」セクションの「ドル円・ブルベアイメージ」という横棒グラフを見てください。"
                            "最新（右側または下側）のグラフについて、ブル（青）・ベア（赤）・ニュートラル（白/グレー）の割合（%）を読み取ってください。"
                            "必ずJSON形式のみで回答してください。例: {\"bull\": 40, \"bear\": 20, \"neutral\": 40}"
                            "数値が読み取れない場合は {\"bull\": null, \"bear\": null, \"neutral\": null} と返してください。"
                        ),
                    },
                ],
            }
        ],
    )

    text = message.content[0].text.strip()
    # JSON部分だけ抽出
    import re
    m = re.search(r'\{[^}]+\}', text)
    if not m:
        raise ValueError(f"JSONが見つかりませんでした: {text}")
    return json.loads(m.group())


def main() -> None:
    today = date.today().isoformat()

    with tempfile.TemporaryDirectory() as tmpdir:
        pdf_path = os.path.join(tmpdir, "smbc.pdf")
        png_path = os.path.join(tmpdir, "page2.png")

        download_pdf(PDF_URL, pdf_path)

        # ブルベアチャートはページ2にある
        pdf_page_to_png(pdf_path, page=2, out_png=png_path)

        values = extract_bull_bear_from_image(png_path)

    bull = values.get("bull")
    bear = values.get("bear")
    neutral = values.get("neutral")

    if bull is None or bear is None:
        print(json.dumps({"error": "数値を読み取れませんでした", "date": today}))
        sys.exit(1)

    ci = bull - bear
    direction = "BULL（ドル高・円安）" if ci > 0 else "BEAR（ドル安・円高）"
    threshold_met = abs(ci) >= THRESHOLD

    result = {
        "bull_pct": bull,
        "bear_pct": bear,
        "neutral_pct": neutral,
        "confidence_index": ci,
        "direction": direction,
        "threshold_met": threshold_met,
        "date": today,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
