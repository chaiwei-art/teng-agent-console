"""工具层测试：真实执行的商城工具与边界情况。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.tools import (  # noqa: E402
    PRODUCTS,
    execute_tool,
    calculate_refund,
    query_logistics,
    query_order,
    search_products,
)


def test_query_order_found():
    r = query_order("SO20261001")
    assert r["order_id"] == "SO20261001"
    assert r["status"] == "已发货"
    assert r["amount"] == 599.0


def test_query_order_missing():
    r = query_order("SO99999999")
    assert "error" in r


def test_query_logistics_tracks():
    r = query_logistics("SO20261001")
    assert r["tracks"]
    assert {"time", "node"} <= set(r["tracks"][0].keys())


def test_query_logistics_no_tracks_for_unpaid():
    r = query_logistics("SO20261003")  # 待付款无物流
    assert r["tracks"] == []


def test_search_products_by_category():
    r = search_products(category="耳机")
    assert r and all(p["category"] == "耳机" for p in r)


def test_search_products_by_keyword():
    r = search_products(keyword="Buds")
    assert r and all("Buds" in p["name"] for p in r)


def test_refund_full_for_shipped():
    r = calculate_refund("SO20261001")
    assert r["refund_amount"] == r["order_amount"]  # 已发货拦截全额


def test_refund_zero_for_unpaid():
    r = calculate_refund("SO20261003")
    assert r["refundable"] == 0.0 or r["refund_amount"] == 0.0


def test_refund_missing_order():
    assert "error" in calculate_refund("SO00000000")


def test_execute_unknown_tool():
    assert "error" in execute_tool("no_such_tool", {})


def test_execute_bad_args():
    assert "error" in execute_tool("query_order", {"wrong_arg": 1})


def test_products_mock_data_invariants():
    assert len(PRODUCTS) >= 5
    assert any(p["stock"] == 0 for p in PRODUCTS)  # 含缺货样例
