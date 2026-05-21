#!/usr/bin/env python3
"""
moomoo MCP Server

Claude Code から moomoo OpenD API を直接呼び出すための MCP サーバー。
OpenD が 127.0.0.1:11111 で起動している状態で使用する。

登録コマンド:
    claude mcp add moomoo -- /opt/homebrew/bin/python3.13 ~/workspace/private/moomoo_mcp_server.py
"""

import json
import sys
import os

sys.path.insert(0, str(os.path.expanduser("~/workspace/momoo-skills/moomooapi/scripts")))

from mcp.server.fastmcp import FastMCP
from moomoo import (
    OpenSecTradeContext,
    OpenQuoteContext,
    TrdEnv,
    SecurityFirm,
    SetPriceReminderOp,
    PriceReminderType,
    PriceReminderFreq,
    RET_OK,
)

mcp = FastMCP("moomoo")

HOST = os.environ.get("FUTU_OPEND_HOST", "127.0.0.1")
PORT = int(os.environ.get("FUTU_OPEND_PORT", "11111"))
SECURITY_FIRM = SecurityFirm.FUTUJP


def _ctx(market="US"):
    from moomoo import TrdMarket
    market_map = {
        "US": TrdMarket.US, "HK": TrdMarket.HK,
        "CN": TrdMarket.CN, "SG": TrdMarket.SG,
    }
    return OpenSecTradeContext(
        filter_trdmarket=market_map.get(market, TrdMarket.US),
        host=HOST, port=PORT,
        security_firm=SECURITY_FIRM,
    )


def _get_real_acc_id(market="US") -> int:
    """実口座のacc_idを自動取得する。環境変数 FUTU_ACC_ID が設定されていればそれを使う。"""
    env_id = os.environ.get("FUTU_ACC_ID", "")
    if env_id.isdigit():
        return int(env_id)
    ctx = _ctx(market)
    try:
        ret, data = ctx.get_acc_list()
        if ret != RET_OK or data.empty:
            raise RuntimeError(f"口座一覧の取得に失敗: {data}")
        real = data[data["trd_env"] == "REAL"]
        if real.empty:
            raise RuntimeError("実口座が見つかりません")
        return int(real.iloc[0]["acc_id"])
    finally:
        ctx.close()


@mcp.tool()
def get_accounts() -> str:
    """moomoo の口座一覧を取得する（実口座・ペーパー両方）"""
    ctx = _ctx("US")
    try:
        ret, data = ctx.get_acc_list()
        accounts = []
        if ret == RET_OK and not data.empty:
            for _, row in data.iterrows():
                accounts.append({
                    "acc_id": int(row["acc_id"]),
                    "acc_type": str(row.get("acc_type", "")),
                    "trd_env": str(row.get("trd_env", "")),
                    "trdmarket_auth": str(row.get("trdmarket_auth", "")),
                    "security_firm": str(row.get("security_firm", "")),
                })
        return json.dumps({"accounts": accounts}, ensure_ascii=False)
    finally:
        ctx.close()


@mcp.tool()
def get_portfolio(trd_env: str = "REAL", currency: str = "USD") -> str:
    """
    保有ポジションと資産情報を取得する。

    Args:
        trd_env: 取引環境 "REAL"（実口座）または "SIMULATE"（ペーパー）
        currency: 通貨 "USD" / "JPY" / "HKD" 等
    """
    env = TrdEnv.REAL if trd_env == "REAL" else TrdEnv.SIMULATE
    acc_id = _get_real_acc_id("US") if trd_env == "REAL" else 1286101
    ctx = _ctx("US")
    try:
        from moomoo import Currency
        ccy_map = {
            "USD": Currency.USD, "JPY": Currency.JPY,
            "HKD": Currency.HKD, "CNH": Currency.CNH,
        }
        ccy = ccy_map.get(currency, Currency.USD)

        ret, acc_data = ctx.accinfo_query(
            trd_env=env, acc_id=acc_id,
            currency=ccy, refresh_cache=True,
        )
        funds = {}
        if ret == RET_OK and not acc_data.empty:
            row = acc_data.iloc[0]
            funds = {
                "total_assets": float(row.get("total_assets", 0)),
                "cash": float(row.get("cash", 0)),
                "market_val": float(row.get("market_val", 0)),
                "currency": str(row.get("currency", currency)),
            }

        ret, pos_data = ctx.position_list_query(
            trd_env=env, acc_id=acc_id, refresh_cache=True,
        )
        positions = []
        if ret == RET_OK and not pos_data.empty:
            for _, row in pos_data.iterrows():
                positions.append({
                    "code": str(row.get("code", "")),
                    "name": str(row.get("stock_name", "")),
                    "qty": int(float(row.get("qty", 0))),
                    "average_cost": float(row.get("average_cost", 0)),
                    "current_price": float(row.get("nominal_price", 0)),
                    "market_val": float(row.get("market_val", 0)),
                    "unrealized_pl": float(row.get("unrealized_pl", 0)),
                    "pl_ratio_pct": float(row.get("pl_ratio_avg_cost", 0)),
                })

        return json.dumps({"funds": funds, "positions": positions}, ensure_ascii=False)
    finally:
        ctx.close()


@mcp.tool()
def get_history_orders(
    market: str = "US",
    trd_env: str = "REAL",
    start: str = "",
    end: str = "",
    limit: int = 200,
) -> str:
    """
    売買履歴（約定済み）を取得する。

    Args:
        market: 市場 "US" / "HK" / "SG"
        trd_env: "REAL" または "SIMULATE"
        start: 開始日 YYYY-MM-DD（省略可）
        end: 終了日 YYYY-MM-DD（省略可）
        limit: 最大取得件数
    """
    env = TrdEnv.REAL if trd_env == "REAL" else TrdEnv.SIMULATE
    acc_id = _get_real_acc_id(market) if trd_env == "REAL" else 1286101
    ctx = _ctx(market)
    try:
        from moomoo import OrderStatus
        kwargs = dict(
            trd_env=env,
            acc_id=acc_id,
            status_filter_list=[OrderStatus.FILLED_ALL],
        )
        if start:
            kwargs["start"] = start
        if end:
            kwargs["end"] = end

        ret, data = ctx.history_order_list_query(**kwargs)
        orders = []
        if ret == RET_OK and not data.empty:
            for _, row in list(data.iterrows())[:limit]:
                orders.append({
                    "order_id": str(row.get("order_id", "")),
                    "code": str(row.get("code", "")),
                    "side": str(row.get("trd_side", "")),
                    "qty": int(float(row.get("qty", 0))),
                    "dealt_qty": int(float(row.get("dealt_qty", 0))),
                    "price": float(row.get("price", 0)),
                    "create_time": str(row.get("create_time", "")),
                })

        return json.dumps({"count": len(orders), "orders": orders}, ensure_ascii=False)
    finally:
        ctx.close()


@mcp.tool()
def get_price_reminders(code: str = "") -> str:
    """
    設定済みの価格アラート一覧を取得する。

    Args:
        code: 銘柄コード例: "US.AAPL"（省略すると全銘柄）
    """
    ctx = OpenQuoteContext(host=HOST, port=PORT)
    try:
        kwargs = {}
        if code:
            kwargs["code"] = code
        ret, data = ctx.get_price_reminder(**kwargs)
        if ret != RET_OK:
            return json.dumps({"error": str(data)})

        reminders = []
        if not data.empty:
            for _, row in data.iterrows():
                reminders.append({
                    "key": str(row.get("key", "")),
                    "code": str(row.get("code", "")),
                    "reminder_type": str(row.get("reminder_type", "")),
                    "reminder_freq": str(row.get("reminder_freq", "")),
                    "value": float(row.get("value", 0)),
                    "note": str(row.get("note", "")),
                    "is_enable": bool(row.get("is_enable", True)),
                })
        return json.dumps({"count": len(reminders), "reminders": reminders}, ensure_ascii=False)
    finally:
        ctx.close()


@mcp.tool()
def set_price_reminder(
    code: str,
    reminder_type: str,
    value: float,
    freq: str = "ONCE_A_DAY",
    note: str = "",
    session: str = "OPEN",
) -> str:
    """
    価格アラートを新規追加する。

    Args:
        code: 銘柄コード 例: "US.AAPL"
        reminder_type: アラート条件（下記から選択）
            PRICE_UP        価格が value 以上に上昇
            PRICE_DOWN      価格が value 以下に下落
            CHANGE_RATE_UP  騰落率が value% 以上に上昇（例: value=5 → +5%）
            CHANGE_RATE_DOWN 騰落率が value% 以下に下落（例: value=-3 → -3%）
            VOLUME_UP       出来高が value 以上
            TURNOVER_RATE_UP 回転率が value% 以上
            FIVE_MIN_CHANGE_RATE_UP   5分変化率が value% 以上
            FIVE_MIN_CHANGE_RATE_DOWN 5分変化率が value% 以下
        value: トリガーとなる値
        freq: 通知頻度 "ONCE"（1回）/ "ONCE_A_DAY"（1日1回）/ "ALWAYS"（毎回）
        note: メモ（省略可）
        session: 対象セッション "OPEN"（通常）/ "US_PRE"（米国プレ）/ "US_AFTER"（時間外）
    """
    type_map = {
        "PRICE_UP": PriceReminderType.PRICE_UP,
        "PRICE_DOWN": PriceReminderType.PRICE_DOWN,
        "CHANGE_RATE_UP": PriceReminderType.CHANGE_RATE_UP,
        "CHANGE_RATE_DOWN": PriceReminderType.CHANGE_RATE_DOWN,
        "VOLUME_UP": PriceReminderType.VOLUME_UP,
        "TURNOVER_RATE_UP": PriceReminderType.TURNOVER_RATE_UP,
        "FIVE_MIN_CHANGE_RATE_UP": PriceReminderType.FIVE_MIN_CHANGE_RATE_UP,
        "FIVE_MIN_CHANGE_RATE_DOWN": PriceReminderType.FIVE_MIN_CHANGE_RATE_DOWN,
        "BID_PRICE_UP": PriceReminderType.BID_PRICE_UP,
        "ASK_PRICE_DOWN": PriceReminderType.ASK_PRICE_DOWN,
    }
    freq_map = {
        "ONCE": PriceReminderFreq.ONCE,
        "ONCE_A_DAY": PriceReminderFreq.ONCE_A_DAY,
        "ALWAYS": PriceReminderFreq.ALWAYS,
    }
    session_map = {
        "OPEN": "OPEN", "US_PRE": "US_PRE", "US_AFTER": "US_AFTER",
    }

    r_type = type_map.get(reminder_type.upper())
    if r_type is None:
        return json.dumps({"error": f"不明な reminder_type: {reminder_type}。選択肢: {list(type_map.keys())}"})

    ctx = OpenQuoteContext(host=HOST, port=PORT)
    try:
        ret, data = ctx.set_price_reminder(
            code=code,
            op=SetPriceReminderOp.ADD,
            reminder_type=r_type,
            reminder_freq=freq_map.get(freq.upper(), PriceReminderFreq.ONCE_A_DAY),
            value=value,
            note=note,
            reminder_session_list=[session_map.get(session.upper(), "OPEN")],
        )
        if ret != RET_OK:
            return json.dumps({"error": str(data)})
        key = int(data) if str(data).isdigit() else str(data)
        return json.dumps({
            "success": True,
            "key": key,
            "code": code,
            "reminder_type": reminder_type,
            "value": value,
            "freq": freq,
        }, ensure_ascii=False)
    finally:
        ctx.close()


@mcp.tool()
def delete_price_reminder(code: str, key: str = "") -> str:
    """
    価格アラートを削除する。

    Args:
        code: 銘柄コード 例: "US.AAPL"
        key: アラートキー（省略すると該当銘柄の全アラートを削除）
    """
    ctx = OpenQuoteContext(host=HOST, port=PORT)
    try:
        op = SetPriceReminderOp.DEL_ALL if not key else SetPriceReminderOp.DEL
        kwargs = dict(code=code, op=op)
        if key:
            kwargs["key"] = int(key)
        ret, data = ctx.set_price_reminder(**kwargs)
        if ret != RET_OK:
            return json.dumps({"error": str(data)})
        return json.dumps({"success": True, "code": code, "deleted_key": key or "ALL"})
    finally:
        ctx.close()


@mcp.tool()
def get_stock_quote(codes: str) -> str:
    """
    米国株のリアルタイム株価スナップショットを取得する。

    Args:
        codes: カンマ区切りの銘柄コード例: "US.AAPL,US.TSLA,US.NVDA"
    """
    from moomoo import OpenQuoteContext
    ctx = OpenQuoteContext(host=HOST, port=PORT)
    try:
        code_list = [c.strip() for c in codes.split(",")]
        ret, data = ctx.get_market_snapshot(code_list)
        if ret != RET_OK:
            return json.dumps({"error": str(data)})

        result = []
        for _, row in data.iterrows():
            result.append({
                "code": str(row.get("code", "")),
                "name": str(row.get("name", "")),
                "last_price": float(row.get("last_price", 0)),
                "change_rate": float(row.get("change_rate", 0)),
                "volume": int(float(row.get("volume", 0))),
                "market_cap": float(row.get("market_cap", 0)),
            })
        return json.dumps({"quotes": result}, ensure_ascii=False)
    finally:
        ctx.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
