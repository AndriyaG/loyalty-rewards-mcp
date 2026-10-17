"""Loyalty Rewards MCP server.

A local-only portfolio demo of a loyalty platform (admin portal + customer
mobile app). All data is fabricated (see loyalty_data.py).

Runs over stdio. stdout carries the MCP protocol, so this file must never
print to stdout; all logging goes to stderr.

Redemption requests are kept in memory only and reset on every restart.
"""

import logging
import math
import sys
from datetime import datetime, timezone
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

import loyalty_data as data

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("loyalty_mcp")

mcp = FastMCP(
    name="Loyalty Rewards MCP",
    instructions=(
        "Demo loyalty platform with an admin portal and a customer mobile app. "
        "All data is fabricated for a portfolio demo. "
        f"Amounts are in generic currency units ({data.CURRENCY}). "
        "Redemption requests are simulated: they are created as PENDING, "
        "never deduct points and are lost when the server restarts."
    ),
)

READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}

MAX_HISTORY_LIMIT = 20

CustomerId = Annotated[str, Field(description="Customer ID, for example 'CUST-001'.")]


# ---------- helpers ----------

def _normalize_id(value: str) -> str:
    return value.strip().upper()


def _get_customer(customer_id: str) -> dict:
    customer = data.CUSTOMERS.get(_normalize_id(customer_id))
    if customer is None:
        known = ", ".join(data.CUSTOMERS)
        raise ToolError(f"Unknown customer_id '{customer_id}'. Known demo IDs: {known}.")
    return customer


def _get_reward(reward_id: str) -> dict:
    reward = data.REWARDS.get(_normalize_id(reward_id))
    if reward is None:
        known = ", ".join(data.REWARDS)
        raise ToolError(f"Unknown reward_id '{reward_id}'. Known demo IDs: {known}.")
    return reward


def _tier_rank(tier: str) -> int:
    return data.TIER_ORDER.index(tier)


def _ineligibility_reasons(customer: dict, reward: dict) -> list[str]:
    """Return why a customer cannot redeem a reward (empty list = eligible).

    DEMO ASSUMPTION: eligibility = enough points + minimum tier + in stock.
    """
    reasons = []
    if customer["points_balance"] < reward["points_cost"]:
        short = reward["points_cost"] - customer["points_balance"]
        reasons.append(
            f"insufficient points: needs {reward['points_cost']}, "
            f"has {customer['points_balance']} ({short} short)"
        )
    if _tier_rank(customer["tier"]) < _tier_rank(reward["min_tier"]):
        reasons.append(f"requires {reward['min_tier']} tier, customer is {customer['tier']}")
    if not reward["in_stock"]:
        reasons.append("reward is out of stock")
    return reasons


# ---------- tools ----------

@mcp.tool(annotations=READ_ONLY)
def get_customer_summary(customer_id: CustomerId) -> dict:
    """Get a customer's profile: name, tier, points balance, earn scheme and
    points earned/redeemed in their recorded transaction history."""
    customer = _get_customer(customer_id)
    history = [t for t in data.TRANSACTIONS if t["customer_id"] == customer["customer_id"]]
    scheme = data.SCHEMES[customer["scheme_id"]]
    return {
        **customer,
        "scheme_name": scheme["name"],
        "transaction_count": len(history),
        "history_points_earned": sum(t["points"] for t in history if t["points"] > 0),
        "history_points_redeemed": -sum(t["points"] for t in history if t["points"] < 0),
        "pending_redemption_requests": sum(
            1 for r in data.REDEMPTION_REQUESTS if r["customer_id"] == customer["customer_id"]
        ),
    }


@mcp.tool(annotations=READ_ONLY)
def get_transaction_history(
    customer_id: CustomerId,
    limit: Annotated[
        int, Field(description=f"How many recent transactions to return (1 to {MAX_HISTORY_LIMIT}).")
    ] = 5,
) -> dict:
    """Get a customer's most recent transactions (earn and redeem), newest first."""
    customer = _get_customer(customer_id)
    if limit < 1 or limit > MAX_HISTORY_LIMIT:
        raise ToolError(f"limit must be between 1 and {MAX_HISTORY_LIMIT}, got {limit}.")
    history = [t for t in data.TRANSACTIONS if t["customer_id"] == customer["customer_id"]]
    history.sort(key=lambda t: t["date"], reverse=True)
    return {
        "customer_id": customer["customer_id"],
        "currency": data.CURRENCY,
        "total_transactions": len(history),
        "returned": len(history[:limit]),
        "transactions": history[:limit],
    }


@mcp.tool(annotations=READ_ONLY)
def list_reward_catalog(
    category: Annotated[
        str,
        Field(description="Optional filter: 'voucher', 'merchandise' or 'experience'. Leave empty for all."),
    ] = "",
) -> dict:
    """List rewards in the catalog with their points cost, minimum tier and stock status."""
    wanted = category.strip().lower()
    if wanted and wanted not in data.REWARD_CATEGORIES:
        raise ToolError(
            f"Unknown category '{category}'. Use one of: {', '.join(data.REWARD_CATEGORIES)}, "
            "or leave empty for all."
        )
    rewards = [r for r in data.REWARDS.values() if not wanted or r["category"] == wanted]
    return {"category": wanted or "all", "count": len(rewards), "rewards": rewards}


@mcp.tool(annotations=READ_ONLY)
def get_eligible_rewards(customer_id: CustomerId) -> dict:
    """List which rewards a customer can redeem right now, and why the others
    are not available (points, tier or stock)."""
    customer = _get_customer(customer_id)
    eligible = []
    not_eligible = []
    for reward in data.REWARDS.values():
        reasons = _ineligibility_reasons(customer, reward)
        if reasons:
            not_eligible.append({"reward_id": reward["reward_id"], "name": reward["name"], "reasons": reasons})
        else:
            eligible.append(reward)
    return {
        "customer_id": customer["customer_id"],
        "tier": customer["tier"],
        "points_balance": customer["points_balance"],
        "eligible": eligible,
        "not_eligible": not_eligible,
        "rule": "DEMO ASSUMPTION: eligible = enough points + minimum tier met + in stock.",
    }


@mcp.tool(annotations=READ_ONLY)
def list_active_schemes() -> dict:
    """List the points-earning schemes that are currently active, with their earn rates."""
    schemes = [s for s in data.SCHEMES.values() if s["active"]]
    return {"currency": data.CURRENCY, "count": len(schemes), "schemes": schemes}


@mcp.tool(annotations=READ_ONLY)
def calculate_points_for_purchase(
    purchase_amount: Annotated[
        float, Field(description=f"Purchase amount in {data.CURRENCY}. Must be greater than 0.")
    ],
    scheme_id: Annotated[str, Field(description="Active scheme ID, for example 'SCH-STANDARD'.")],
) -> dict:
    """Calculate how many points a purchase would earn under a scheme.
    Read-only: this does not award any points."""
    if not math.isfinite(purchase_amount) or purchase_amount <= 0:
        raise ToolError(f"purchase_amount must be a number greater than 0, got {purchase_amount}.")
    scheme = data.SCHEMES.get(_normalize_id(scheme_id))
    if scheme is None:
        raise ToolError(f"Unknown scheme_id '{scheme_id}'. Known demo IDs: {', '.join(data.SCHEMES)}.")
    if not scheme["active"]:
        raise ToolError(f"Scheme '{scheme['scheme_id']}' is not active. Use list_active_schemes to see options.")

    # DEMO ASSUMPTION: points = full blocks spent x points per block, rounded down.
    if purchase_amount < scheme["min_purchase"]:
        full_blocks = 0
        points = 0
    else:
        full_blocks = math.floor(purchase_amount / scheme["block_size"])
        points = full_blocks * scheme["points_per_block"]

    return {
        "scheme_id": scheme["scheme_id"],
        "purchase_amount": purchase_amount,
        "currency": data.CURRENCY,
        "points": points,
        "calculation": (
            f"floor({purchase_amount} / {scheme['block_size']}) = {full_blocks} blocks "
            f"x {scheme['points_per_block']} points = {points}"
        ),
        "min_purchase": scheme["min_purchase"],
        "rule": "DEMO ASSUMPTION: points per full block of spend, rounded down; "
        "purchases below min_purchase earn 0.",
    }


@mcp.tool(annotations=READ_ONLY)
def get_campaign_performance(
    campaign_id: Annotated[
        str, Field(description="Optional campaign ID, for example 'CMP-001'. Leave empty for all campaigns.")
    ] = "",
) -> dict:
    """Get admin-portal performance metrics for one campaign or all campaigns:
    participation rate, redemption rate and return on investment."""
    if campaign_id.strip():
        campaign = data.CAMPAIGNS.get(_normalize_id(campaign_id))
        if campaign is None:
            raise ToolError(
                f"Unknown campaign_id '{campaign_id}'. Known demo IDs: {', '.join(data.CAMPAIGNS)}."
            )
        campaigns = [campaign]
    else:
        campaigns = list(data.CAMPAIGNS.values())

    results = []
    for c in campaigns:
        # DEMO ASSUMPTION: these metric formulas are simplified for the demo.
        participation = c["customers_participated"] / c["customers_targeted"] * 100
        redemption = c["points_redeemed"] / c["points_issued"] * 100 if c["points_issued"] else 0.0
        roi = (c["incremental_revenue"] - c["cost"]) / c["cost"] * 100 if c["cost"] else None
        results.append({
            **c,
            "participation_rate_pct": round(participation, 1),
            "redemption_rate_pct": round(redemption, 1),
            "roi_pct": round(roi, 1) if roi is not None else None,
        })

    return {
        "currency": data.CURRENCY,
        "count": len(results),
        "campaigns": results,
        "rule": "DEMO ASSUMPTION: participation = participated / targeted; "
        "redemption = points redeemed / points issued; ROI = (revenue - cost) / cost.",
    }


@mcp.tool(
    annotations={
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    }
)
def create_redemption_request(
    customer_id: CustomerId,
    reward_id: Annotated[str, Field(description="Reward ID, for example 'RWD-001'.")],
) -> dict:
    """Create a SIMULATED redemption request with status PENDING.
    It does not deduct points, take payment or contact any external service.
    Requests are stored in memory and are lost when the server restarts."""
    customer = _get_customer(customer_id)
    reward = _get_reward(reward_id)
    reasons = _ineligibility_reasons(customer, reward)
    if reasons:
        raise ToolError(
            f"Cannot redeem {reward['reward_id']} for {customer['customer_id']}: {'; '.join(reasons)}."
        )

    request = {
        "request_id": f"REQ-{len(data.REDEMPTION_REQUESTS) + 1:04d}",
        "customer_id": customer["customer_id"],
        "reward_id": reward["reward_id"],
        "reward_name": reward["name"],
        "points_cost": reward["points_cost"],
        "status": "PENDING",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    data.REDEMPTION_REQUESTS.append(request)
    logger.info("Created simulated redemption request %s", request["request_id"])
    return {
        **request,
        "points_balance_unchanged": customer["points_balance"],
        "note": "Simulated only: points were NOT deducted and nothing was paid or sent. "
        "This request is held in memory and resets when the server restarts.",
    }


if __name__ == "__main__":
    logger.info("Starting Loyalty Rewards MCP server over stdio")
    # The banner triggers a PyPI version check; this demo stays offline.
    mcp.run(transport="http", host="127.0.0.1", port=8000, show_banner=False)
