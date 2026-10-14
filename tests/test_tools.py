"""Unit tests for the 8 tools, calling the Python functions directly.

The expected values come from the fabricated data in loyalty_data.py and the
demo assumptions documented there and in README.md.
"""

import math
import os
import socket

import pytest
from fastmcp.exceptions import ToolError

import loyalty_data as data
from server import (
    calculate_points_for_purchase,
    create_redemption_request,
    get_campaign_performance,
    get_customer_summary,
    get_eligible_rewards,
    get_transaction_history,
    list_active_schemes,
    list_reward_catalog,
)


# ---------- test environment ----------

def test_no_groq_key_and_no_network():
    assert "GROQ_API_KEY" not in os.environ
    with socket.socket() as sock, pytest.raises(RuntimeError, match="Network access is blocked"):
        sock.connect(("203.0.113.1", 443))  # TEST-NET address, never actually contacted


# ---------- 1. get_customer_summary ----------

@pytest.mark.parametrize("customer_id", list(data.CUSTOMERS))
def test_customer_summary_valid_ids(customer_id):
    result = get_customer_summary(customer_id)
    customer = data.CUSTOMERS[customer_id]
    assert result["customer_id"] == customer_id
    assert result["name"] == customer["name"]
    assert result["tier"] == customer["tier"]
    assert result["points_balance"] == customer["points_balance"]


def test_customer_summary_output_types():
    result = get_customer_summary("CUST-001")
    assert isinstance(result, dict)
    assert isinstance(result["name"], str)
    assert isinstance(result["points_balance"], int)
    assert isinstance(result["transaction_count"], int)
    assert isinstance(result["history_points_earned"], int)
    assert isinstance(result["history_points_redeemed"], int)
    assert result["scheme_name"] == "Gold Member Earn"


def test_customer_summary_history_totals():
    result = get_customer_summary("CUST-002")
    assert result["transaction_count"] == 4
    assert result["history_points_earned"] == 45 + 99 + 27
    assert result["history_points_redeemed"] == 500


def test_customer_id_is_trimmed_and_case_insensitive():
    assert get_customer_summary("  cust-003 ")["customer_id"] == "CUST-003"


@pytest.mark.parametrize("bad_id", ["CUST-999", "", "123", "RWD-001"])
def test_customer_summary_unknown_id(bad_id):
    with pytest.raises(ToolError, match="Unknown customer_id"):
        get_customer_summary(bad_id)


# ---------- 2. get_transaction_history ----------

def test_history_default_limit_is_five_newest_first():
    result = get_transaction_history("CUST-001")
    dates = [t["date"] for t in result["transactions"]]
    assert result["total_transactions"] == 7
    assert result["returned"] == 5
    assert dates == sorted(dates, reverse=True)
    assert result["transactions"][0]["transaction_id"] == "TXN-1014"


def test_history_only_contains_that_customer():
    result = get_transaction_history("CUST-002", limit=20)
    assert {t["customer_id"] for t in result["transactions"]} == {"CUST-002"}


@pytest.mark.parametrize("limit, expected", [(1, 1), (3, 3), (7, 7), (20, 7)])
def test_history_valid_limits(limit, expected):
    assert get_transaction_history("CUST-001", limit=limit)["returned"] == expected


@pytest.mark.parametrize("limit", [0, -1, 21, 1000])
def test_history_invalid_limits(limit):
    with pytest.raises(ToolError, match="limit must be between 1 and 20"):
        get_transaction_history("CUST-001", limit=limit)


def test_history_empty_for_customer_without_transactions():
    result = get_transaction_history("CUST-004")
    assert result["total_transactions"] == 0
    assert result["transactions"] == []


def test_history_unknown_customer():
    with pytest.raises(ToolError, match="Unknown customer_id"):
        get_transaction_history("CUST-404")


def test_history_output_types():
    result = get_transaction_history("CUST-001", limit=2)
    assert result["currency"] == data.CURRENCY
    for txn in result["transactions"]:
        assert isinstance(txn["transaction_id"], str)
        assert txn["type"] in {"earn", "redeem"}
        assert isinstance(txn["points"], int)


# ---------- 3. list_reward_catalog ----------

def test_catalog_all_rewards():
    result = list_reward_catalog()
    assert result["category"] == "all"
    assert result["count"] == len(data.REWARDS) == 6
    assert {r["reward_id"] for r in result["rewards"]} == set(data.REWARDS)


@pytest.mark.parametrize(
    "category, expected_ids",
    [
        ("voucher", {"RWD-001", "RWD-002"}),
        ("merchandise", {"RWD-003", "RWD-004"}),
        ("experience", {"RWD-005", "RWD-006"}),
        ("  Voucher ", {"RWD-001", "RWD-002"}),
    ],
)
def test_catalog_category_filter(category, expected_ids):
    result = list_reward_catalog(category)
    assert {r["reward_id"] for r in result["rewards"]} == expected_ids
    assert result["count"] == len(expected_ids)


def test_catalog_unknown_category():
    with pytest.raises(ToolError, match="Unknown category 'cars'"):
        list_reward_catalog("cars")


def test_catalog_output_types():
    for reward in list_reward_catalog()["rewards"]:
        assert isinstance(reward["points_cost"], int)
        assert isinstance(reward["in_stock"], bool)
        assert reward["min_tier"] in data.TIER_ORDER


# ---------- 4. get_eligible_rewards ----------

def _ids(rewards):
    return {r["reward_id"] for r in rewards}


def _reasons(result):
    return {r["reward_id"]: r["reasons"] for r in result["not_eligible"]}


def test_eligible_rewards_gold_customer():
    result = get_eligible_rewards("CUST-001")
    assert _ids(result["eligible"]) == {"RWD-001", "RWD-002", "RWD-003", "RWD-004", "RWD-005"}
    assert _reasons(result) == {"RWD-006": ["reward is out of stock"]}


def test_eligible_rewards_silver_customer():
    result = get_eligible_rewards("CUST-002")
    assert _ids(result["eligible"]) == {"RWD-001", "RWD-002", "RWD-003"}
    reasons = _reasons(result)
    assert any("insufficient points" in r for r in reasons["RWD-004"])
    assert any("requires Gold tier" in r for r in reasons["RWD-005"])
    assert reasons["RWD-006"] == ["reward is out of stock"]


def test_eligible_rewards_bronze_customer_low_points():
    result = get_eligible_rewards("CUST-003")
    assert _ids(result["eligible"]) == {"RWD-001"}
    assert any("requires Silver tier" in r for r in _reasons(result)["RWD-003"])


def test_eligible_rewards_zero_points_customer_gets_nothing():
    result = get_eligible_rewards("CUST-004")
    assert result["eligible"] == []
    assert len(result["not_eligible"]) == 6


def test_eligible_plus_ineligible_covers_whole_catalog():
    for customer_id in data.CUSTOMERS:
        result = get_eligible_rewards(customer_id)
        assert _ids(result["eligible"]) | _ids(result["not_eligible"]) == set(data.REWARDS)
        assert not _ids(result["eligible"]) & _ids(result["not_eligible"])


def test_eligible_rewards_unknown_customer():
    with pytest.raises(ToolError, match="Unknown customer_id"):
        get_eligible_rewards("NOBODY")


# ---------- 5. list_active_schemes ----------

def test_active_schemes_exclude_inactive():
    result = list_active_schemes()
    assert {s["scheme_id"] for s in result["schemes"]} == {"SCH-STANDARD", "SCH-GOLD", "SCH-WEEKEND"}
    assert result["count"] == 3
    assert all(s["active"] is True for s in result["schemes"])


def test_active_schemes_output_types():
    result = list_active_schemes()
    assert result["currency"] == data.CURRENCY
    for scheme in result["schemes"]:
        assert isinstance(scheme["points_per_block"], int)
        assert isinstance(scheme["block_size"], int) and scheme["block_size"] > 0
        assert isinstance(scheme["min_purchase"], int)


# ---------- 6. calculate_points_for_purchase ----------

@pytest.mark.parametrize(
    "amount, scheme_id, expected_points",
    [
        (100, "SCH-STANDARD", 1),
        (99.99, "SCH-STANDARD", 0),
        (1250, "SCH-STANDARD", 12),
        (1299.99, "SCH-STANDARD", 12),
        (1250, "SCH-GOLD", 36),
        (499.99, "SCH-WEEKEND", 0),
        (500, "SCH-WEEKEND", 20),
        (549, "SCH-WEEKEND", 20),
        (550, "SCH-WEEKEND", 22),
        (0.01, "SCH-GOLD", 0),
    ],
)
def test_points_calculation(amount, scheme_id, expected_points):
    result = calculate_points_for_purchase(amount, scheme_id)
    assert result["points"] == expected_points
    assert isinstance(result["points"], int)


def test_points_calculation_is_deterministic():
    results = {calculate_points_for_purchase(777.77, "SCH-GOLD")["points"] for _ in range(5)}
    assert results == {21}


def test_points_calculation_output():
    result = calculate_points_for_purchase(1250, "sch-standard")
    assert result["scheme_id"] == "SCH-STANDARD"
    assert result["currency"] == data.CURRENCY
    assert "DEMO ASSUMPTION" in result["rule"]
    assert "12 blocks" in result["calculation"]


@pytest.mark.parametrize("amount", [0, -0.01, -50, math.nan, math.inf, -math.inf])
def test_points_invalid_amounts(amount):
    with pytest.raises(ToolError, match="purchase_amount must be a number greater than 0"):
        calculate_points_for_purchase(amount, "SCH-STANDARD")


def test_points_unknown_scheme():
    with pytest.raises(ToolError, match="Unknown scheme_id"):
        calculate_points_for_purchase(100, "SCH-NOPE")


def test_points_inactive_scheme():
    with pytest.raises(ToolError, match="not active"):
        calculate_points_for_purchase(100, "SCH-LEGACY")


# ---------- 7. get_campaign_performance ----------

def test_campaigns_all():
    result = get_campaign_performance()
    assert result["count"] == 3
    assert {c["campaign_id"] for c in result["campaigns"]} == set(data.CAMPAIGNS)


def test_campaign_single_lookup_metrics():
    result = get_campaign_performance("cmp-001")
    assert result["count"] == 1
    campaign = result["campaigns"][0]
    assert campaign["campaign_id"] == "CMP-001"
    assert campaign["participation_rate_pct"] == 23.0      # 2760 / 12000
    assert campaign["redemption_rate_pct"] == 33.2         # 61000 / 184000
    assert campaign["roi_pct"] == 300.0                    # (920000 - 230000) / 230000


def test_campaign_with_no_activity_has_safe_metrics():
    campaign = get_campaign_performance("CMP-003")["campaigns"][0]
    assert campaign["participation_rate_pct"] == 0.0
    assert campaign["redemption_rate_pct"] == 0.0
    assert campaign["roi_pct"] is None


def test_campaign_output_types():
    for campaign in get_campaign_performance()["campaigns"]:
        assert isinstance(campaign["participation_rate_pct"], float)
        assert isinstance(campaign["redemption_rate_pct"], float)
        assert campaign["roi_pct"] is None or isinstance(campaign["roi_pct"], float)
        assert campaign["status"] in {"completed", "active", "scheduled"}


def test_campaign_unknown_id():
    with pytest.raises(ToolError, match="Unknown campaign_id"):
        get_campaign_performance("CMP-404")


# ---------- 8. create_redemption_request ----------

def test_redemption_success_is_pending_and_simulated():
    balance_before = data.CUSTOMERS["CUST-002"]["points_balance"]
    result = create_redemption_request("CUST-002", "RWD-003")

    assert result["status"] == "PENDING"
    assert result["request_id"] == "REQ-0001"
    assert result["customer_id"] == "CUST-002"
    assert result["reward_id"] == "RWD-003"
    assert result["points_cost"] == 800
    assert isinstance(result["created_at"], str)
    assert "NOT deducted" in result["note"]

    assert data.CUSTOMERS["CUST-002"]["points_balance"] == balance_before
    assert result["points_balance_unchanged"] == balance_before
    assert len(data.REDEMPTION_REQUESTS) == 1


def test_redemption_ids_are_sequential_and_shown_in_summary():
    first = create_redemption_request("CUST-001", "RWD-001")
    second = create_redemption_request("CUST-001", "RWD-002")
    assert (first["request_id"], second["request_id"]) == ("REQ-0001", "REQ-0002")
    assert get_customer_summary("CUST-001")["pending_redemption_requests"] == 2


def test_redemption_insufficient_points():
    with pytest.raises(ToolError, match=r"insufficient points: needs 500, has 180 \(320 short\)"):
        create_redemption_request("CUST-003", "RWD-002")
    assert data.REDEMPTION_REQUESTS == []


def test_redemption_zero_balance():
    with pytest.raises(ToolError, match="insufficient points"):
        create_redemption_request("CUST-004", "RWD-001")


def test_redemption_tier_too_low():
    with pytest.raises(ToolError, match="requires Gold tier"):
        create_redemption_request("CUST-002", "RWD-005")


def test_redemption_out_of_stock():
    with pytest.raises(ToolError, match="out of stock"):
        create_redemption_request("CUST-001", "RWD-006")
    assert data.REDEMPTION_REQUESTS == []


def test_redemption_unknown_customer():
    with pytest.raises(ToolError, match="Unknown customer_id"):
        create_redemption_request("CUST-999", "RWD-001")


def test_redemption_unknown_reward():
    with pytest.raises(ToolError, match="Unknown reward_id"):
        create_redemption_request("CUST-001", "RWD-999")
