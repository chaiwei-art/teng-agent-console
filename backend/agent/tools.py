"""Mock 商城数据 + Agent 可调用的工具集。

工具是真实执行的（查字典/列表），只有"大脑"（LLM 决策）是脚本化的，
这样 demo 无需 API Key 也能完整跑通 ReAct 循环。
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable, Dict, List

# ---------------------------------------------------------------- mock 数据

ORDERS: Dict[str, Dict[str, Any]] = {
    "SO20261001": {
        "order_id": "SO20261001",
        "product": "Teng Buds Pro 3 真无线耳机",
        "amount": 599.0,
        "status": "已发货",
        "pay_time": "2026-10-18 21:34",
        "logistics": [
            {"time": "10-19 09:12", "node": "深圳分拨中心，已发出"},
            {"time": "10-19 23:40", "node": "广州转运中心，运输中"},
            {"time": "10-20 14:05", "node": "到达武汉江汉区网点"},
        ],
    },
    "SO20261002": {
        "order_id": "SO20261002",
        "product": "Teng Phone 15 Ultra 手机壳（磨砂黑）",
        "amount": 69.0,
        "status": "已完成",
        "pay_time": "2026-10-10 10:02",
        "logistics": [
            {"time": "10-11 08:30", "node": "已签收，签收人：本人"},
        ],
    },
    "SO20261003": {
        "order_id": "SO20261003",
        "product": "Teng Watch S4 智能手表",
        "amount": 1299.0,
        "status": "待付款",
        "pay_time": None,
        "logistics": [],
    },
}

PRODUCTS: List[Dict[str, Any]] = [
    {"name": "Teng Buds Pro 3", "category": "耳机", "price": 599, "stock": 128, "rating": 4.8},
    {"name": "Teng Buds Air", "category": "耳机", "price": 299, "stock": 340, "rating": 4.5},
    {"name": "Teng Phone 15 Ultra", "category": "手机", "price": 4999, "stock": 56, "rating": 4.9},
    {"name": "Teng Phone 15", "category": "手机", "price": 3299, "stock": 200, "rating": 4.7},
    {"name": "Teng Watch S4", "category": "手表", "price": 1299, "stock": 89, "rating": 4.6},
    {"name": "Teng Pad Air 11", "category": "平板", "price": 1899, "stock": 0, "rating": 4.4},
]

REFUND_POLICY = {
    "unshipped": {"ratio": 1.0, "note": "未发货订单全额退款"},
    "shipped": {"ratio": 1.0, "note": "已发货但未签收，可拦截退款"},
    "delivered_7d": {"ratio": 1.0, "note": "签收 7 天内，无理由全额退款"},
    "delivered_30d": {"ratio": 0.6, "note": "签收 7-30 天，按 60% 部分退款"},
}


# ---------------------------------------------------------------- 工具执行器

def _simulate_latency(low: float = 0.25, high: float = 0.7) -> None:
    time.sleep(random.uniform(low, high))


def query_order(order_id: str) -> Dict[str, Any]:
    _simulate_latency()
    order = ORDERS.get(order_id)
    if not order:
        return {"error": f"未找到订单 {order_id}，请确认单号是否正确"}
    return {
        "order_id": order["order_id"],
        "product": order["product"],
        "amount": order["amount"],
        "status": order["status"],
        "pay_time": order["pay_time"],
    }


def query_logistics(order_id: str) -> Dict[str, Any]:
    _simulate_latency()
    order = ORDERS.get(order_id)
    if not order:
        return {"error": f"未找到订单 {order_id}"}
    if not order["logistics"]:
        return {"order_id": order_id, "status": order["status"], "tracks": [], "note": "暂无物流信息"}
    return {"order_id": order_id, "status": order["status"], "tracks": order["logistics"]}


def search_products(keyword: str = "", category: str = "") -> List[Dict[str, Any]]:
    _simulate_latency(0.2, 0.5)
    result = PRODUCTS
    if category:
        result = [p for p in result if p["category"] == category]
    if keyword:
        result = [p for p in result if keyword.lower() in p["name"].lower() or keyword in p["category"]]
    return result[:5]


def calculate_refund(order_id: str, reason: str = "无理由") -> Dict[str, Any]:
    _simulate_latency()
    order = ORDERS.get(order_id)
    if not order:
        return {"error": f"未找到订单 {order_id}"}
    status = order["status"]
    if status == "待付款":
        return {"order_id": order_id, "refundable": 0.0, "note": "订单未付款，无需退款"}
    tier = "delivered_7d" if status == "已完成" else ("shipped" if status == "已发货" else "unshipped")
    policy = REFUND_POLICY[tier]
    refund = round(order["amount"] * policy["ratio"], 2)
    return {
        "order_id": order_id,
        "order_amount": order["amount"],
        "refund_amount": refund,
        "policy_note": policy["note"],
        "reason": reason,
    }


def get_inventory(product_name: str) -> Dict[str, Any]:
    _simulate_latency(0.15, 0.4)
    for p in PRODUCTS:
        if product_name.lower() in p["name"].lower():
            return {"product": p["name"], "stock": p["stock"], "available": p["stock"] > 0}
    return {"error": f"未找到商品 {product_name}"}


# ---------------------------------------------------------------- 工具注册表

TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "query_order",
        "description": "根据订单号查询订单基本信息（商品、金额、状态、支付时间）",
        "parameters": {"order_id": {"type": "string", "description": "订单号，如 SO20261001"}},
        "fn": query_order,
    },
    {
        "name": "query_logistics",
        "description": "根据订单号查询物流轨迹",
        "parameters": {"order_id": {"type": "string", "description": "订单号"}},
        "fn": query_logistics,
    },
    {
        "name": "search_products",
        "description": "搜索在售商品，支持关键词或品类过滤",
        "parameters": {
            "keyword": {"type": "string", "description": "商品名关键词"},
            "category": {"type": "string", "description": "品类：手机/耳机/手表/平板"},
        },
        "fn": search_products,
    },
    {
        "name": "calculate_refund",
        "description": "计算订单可退款金额（根据订单状态匹配退款政策）",
        "parameters": {
            "order_id": {"type": "string", "description": "订单号"},
            "reason": {"type": "string", "description": "退款原因"},
        },
        "fn": calculate_refund,
    },
    {
        "name": "get_inventory",
        "description": "查询指定商品的库存",
        "parameters": {"product_name": {"type": "string", "description": "商品名称"}},
        "fn": get_inventory,
    },
]

TOOL_MAP: Dict[str, Callable[..., Any]] = {spec["name"]: spec["fn"] for spec in TOOL_SPECS}


def execute_tool(name: str, args: Dict[str, Any]) -> Any:
    fn = TOOL_MAP.get(name)
    if fn is None:
        return {"error": f"未知工具: {name}"}
    try:
        return fn(**args)
    except TypeError as exc:
        return {"error": f"参数错误: {exc}"}
