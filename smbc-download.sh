#!/bin/bash
# SMBC FXマーケットレポートをダウンロードしてブルベアチャートページをPNGに変換する
# 出力: /tmp/smbc_bullbear.png

set -e

PDF_URL="https://www.smbc.co.jp/market/pdf/comment.pdf"
PDF_TMP="/tmp/smbc_report.pdf"
PPM_PREFIX="/tmp/smbc_page"
PNG_OUT="/tmp/smbc_bullbear.png"

echo "Downloading SMBC FX Market Report..."
curl -sL -A "Mozilla/5.0" -o "$PDF_TMP" "$PDF_URL"

echo "Converting page 2 to PNG..."
pdftoppm -r 200 -f 2 -l 2 "$PDF_TMP" "$PPM_PREFIX"
sips -s format png "${PPM_PREFIX}-2.ppm" --out "$PNG_OUT" > /dev/null

rm -f "${PPM_PREFIX}-2.ppm" "$PDF_TMP"

echo "Done: $PNG_OUT"
echo "Date: $(date '+%Y-%m-%d %H:%M')"
