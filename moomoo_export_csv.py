#!/usr/bin/env python3
"""
moomoo 米国株 CSV エクスポート

OpenD が 127.0.0.1:11111 で起動している状態で実行する。

Usage:
    python moomoo_export_csv.py                         # 本番口座・全期間
    python moomoo_export_csv.py --trd-env SIMULATE      # ペーパートレード
    python moomoo_export_csv.py --start 2025-01-01 --end 2025-12-31
    python moomoo_export_csv.py --out-dir ~/Downloads

出力:
    positions_YYYYMMDD_HHMMSS.csv   保有ポジション
    orders_YYYYMMDD_HHMMSS.csv      売買履歴（成立済み）
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKILL_SCRIPTS = Path(__file__).parent.parent / "momoo-skills" / "moomooapi" / "scripts" / "trade"
PYTHON = sys.executable


def run_script(script: str, extra_args: list[str]) -> dict:
    cmd = [PYTHON, str(SKILL_SCRIPTS / script), "--json"] + extra_args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode not in (0,):
        print(f"[ERROR] {script}: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    # ログ行を除外してJSONのみ抽出（stdout にログが混入する場合の対策）
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            return json.loads(line)
    raise ValueError(f"JSON output not found in {script} output:\n{result.stdout}")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        print(f"  データなし: {path.name} はスキップ")
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  保存: {path}  ({len(rows)} 行)")


def export_positions(args, out_dir: Path, suffix: str) -> None:
    print("\n📊 保有ポジション取得中...")
    extra = build_common_args(args, include_currency=True)
    data = run_script("get_portfolio.py", extra)

    positions = data.get("positions", [])
    # 米国株のみ絞り込み（US. プレフィックス）
    us_positions = [p for p in positions if str(p.get("code", "")).startswith("US.")]

    funds = data.get("funds", {})
    print(f"  総資産: {funds.get('total_assets', 'N/A')}  通貨: {funds.get('currency', 'N/A')}")
    print(f"  全ポジション: {len(positions)} 件  米国株: {len(us_positions)} 件")

    # CSV 用にフィールドを整形
    rows = []
    for p in us_positions:
        rows.append({
            "取得日時": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "コード": p["code"],
            "銘柄名": p["name"],
            "保有数量": int(p["qty"]),
            "売却可能数量": int(p["can_sell_qty"]),
            "平均取得単価": p["average_cost"],
            "現在値": p["nominal_price"],
            "評価額": p["market_val"],
            "含み損益": p["unrealized_pl"],
            "損益率(%)": round(p["pl_ratio_avg_cost"], 2),
            "実現損益": p["realized_pl"],
            "当日損益": p["today_pl_val"],
        })

    path = out_dir / f"positions_{suffix}.csv"
    write_csv(path, rows)


def export_orders(args, out_dir: Path, suffix: str) -> None:
    print("\n📋 売買履歴取得中...")
    extra = build_common_args(args, include_currency=False)
    if args.start:
        extra += ["--start", args.start]
    if args.end:
        extra += ["--end", args.end]
    extra += ["--market", "US", "--status", "FILLED_ALL", "--limit", "1000"]

    data = run_script("get_history_orders.py", extra)
    orders = data.get("orders", [])
    print(f"  取得件数: {len(orders)} 件")

    rows = []
    for o in orders:
        rows.append({
            "注文ID": o["order_id"],
            "コード": o["code"],
            "売買": "買" if "BUY" in str(o["side"]).upper() else "売",
            "注文数量": int(o["qty"]),
            "約定数量": int(o["dealt_qty"]),
            "注文単価": o["price"],
            "ステータス": o["status"],
            "注文日時": o["create_time"],
            "更新日時": o["updated_time"],
        })

    path = out_dir / f"orders_{suffix}.csv"
    write_csv(path, rows)


def build_common_args(args, include_currency: bool = False) -> list[str]:
    extra = ["--trd-env", args.trd_env]
    if args.acc_id:
        extra += ["--acc-id", str(args.acc_id)]
    if args.security_firm:
        extra += ["--security-firm", args.security_firm]
    if include_currency and hasattr(args, "currency") and args.currency:
        extra += ["--currency", args.currency]
    return extra


def main():
    parser = argparse.ArgumentParser(description="moomoo 米国株 CSV エクスポート")
    parser.add_argument("--trd-env", choices=["REAL", "SIMULATE"], default="REAL",
                        help="取引環境 (default: REAL)")
    parser.add_argument("--acc-id", type=int, default=None, help="口座ID")
    parser.add_argument("--security-firm",
                        choices=["FUTUSECURITIES", "FUTUINC", "FUTUSG", "FUTUAU", "FUTUCA", "FUTUJP", "FUTUMY"],
                        default="FUTUJP", help="証券会社識別子 (default: FUTUJP)")
    parser.add_argument("--currency", choices=["USD", "HKD", "JPY", "CNH", "AUD", "CAD", "MYR", "SGD"],
                        default="USD", help="通貨 (default: USD)")
    parser.add_argument("--start", default=None, help="履歴開始日 YYYY-MM-DD")
    parser.add_argument("--end", default=None, help="履歴終了日 YYYY-MM-DD")
    parser.add_argument("--out-dir", default=".", help="CSV 保存先ディレクトリ (default: カレント)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    env_label = "本番" if args.trd_env == "REAL" else "ペーパー"

    print(f"=== moomoo CSV エクスポート ({env_label}環境) ===")
    print(f"保存先: {out_dir}")

    export_positions(args, out_dir, suffix)
    export_orders(args, out_dir, suffix)

    print("\n✅ 完了")


if __name__ == "__main__":
    main()
