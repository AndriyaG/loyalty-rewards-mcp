"""Fabricated in-memory data for the Loyalty Rewards MCP demo.

Everything here is invented for a portfolio demo. No real people, brands,
prices or business rules. Every rule below is a DEMO ASSUMPTION.

Stable demo IDs:
    Customers:  CUST-001, CUST-002, CUST-003, CUST-004
    Schemes:    SCH-STANDARD, SCH-GOLD, SCH-WEEKEND, SCH-LEGACY (inactive)
    Rewards:    RWD-001 ... RWD-006
    Campaigns:  CMP-001, CMP-002, CMP-003
    Transactions: TXN-1001 ... TXN-1014

State: REDEMPTION_REQUESTS lives in memory only. It starts empty and is
reset every time the server restarts.
"""

# DEMO ASSUMPTION: a generic, made-up currency. Amounts are in "currency units".
CURRENCY = "CU"

# DEMO ASSUMPTION: tiers from lowest to highest. A reward with min_tier "Silver"
# is available to Silver and Gold customers.
TIER_ORDER = ["Bronze", "Silver", "Gold"]


# DEMO ASSUMPTION: each scheme awards `points_per_block` points for every full
# `block_size` currency units spent, rounded down. Purchases below
# `min_purchase` earn nothing.
SCHEMES = {
    "SCH-STANDARD": {
        "scheme_id": "SCH-STANDARD",
        "name": "Standard Earn",
        "description": "1 point per 100 CU spent.",
        "points_per_block": 1,
        "block_size": 100,
        "min_purchase": 0,
        "active": True,
    },
    "SCH-GOLD": {
        "scheme_id": "SCH-GOLD",
        "name": "Gold Member Earn",
        "description": "3 points per 100 CU spent, for Gold tier members.",
        "points_per_block": 3,
        "block_size": 100,
        "min_purchase": 0,
        "active": True,
    },
    "SCH-WEEKEND": {
        "scheme_id": "SCH-WEEKEND",
        "name": "Weekend Booster",
        "description": "2 points per 50 CU spent on purchases of 500 CU or more.",
        "points_per_block": 2,
        "block_size": 50,
        "min_purchase": 500,
        "active": True,
    },
    "SCH-LEGACY": {
        "scheme_id": "SCH-LEGACY",
        "name": "Legacy Launch Offer",
        "description": "Retired launch scheme, kept to show inactive schemes.",
        "points_per_block": 5,
        "block_size": 100,
        "min_purchase": 0,
        "active": False,
    },
}


# DEMO ASSUMPTION: points_balance includes points from before the recorded
# transaction history, so it does not equal the sum of TRANSACTIONS.
CUSTOMERS = {
    "CUST-001": {
        "customer_id": "CUST-001",
        "name": "Asha Demo",
        "tier": "Gold",
        "points_balance": 4200,
        "scheme_id": "SCH-GOLD",
        "member_since": "2023-02-14",
        "preferred_channel": "mobile_app",
    },
    "CUST-002": {
        "customer_id": "CUST-002",
        "name": "Ben Sample",
        "tier": "Silver",
        "points_balance": 1350,
        "scheme_id": "SCH-STANDARD",
        "member_since": "2024-06-01",
        "preferred_channel": "mobile_app",
    },
    "CUST-003": {
        "customer_id": "CUST-003",
        "name": "Chen Placeholder",
        "tier": "Bronze",
        "points_balance": 180,
        "scheme_id": "SCH-STANDARD",
        "member_since": "2025-11-20",
        "preferred_channel": "in_store",
    },
    "CUST-004": {
        "customer_id": "CUST-004",
        "name": "Dana Fictional",
        "tier": "Silver",
        "points_balance": 0,
        "scheme_id": "SCH-STANDARD",
        "member_since": "2026-08-03",
        "preferred_channel": "mobile_app",
    },
}


# type "earn" adds points, type "redeem" removes points (negative `points`).
TRANSACTIONS = [
    {"transaction_id": "TXN-1001", "customer_id": "CUST-001", "date": "2026-07-02", "type": "earn", "amount": 12500, "points": 375, "description": "Electronics purchase"},
    {"transaction_id": "TXN-1002", "customer_id": "CUST-001", "date": "2026-07-19", "type": "redeem", "amount": 0, "points": -1500, "description": "Redeemed RWD-004"},
    {"transaction_id": "TXN-1003", "customer_id": "CUST-001", "date": "2026-08-05", "type": "earn", "amount": 3400, "points": 102, "description": "Grocery purchase"},
    {"transaction_id": "TXN-1004", "customer_id": "CUST-001", "date": "2026-08-28", "type": "earn", "amount": 8900, "points": 267, "description": "Home goods purchase"},
    {"transaction_id": "TXN-1005", "customer_id": "CUST-001", "date": "2026-09-14", "type": "earn", "amount": 2100, "points": 63, "description": "Cafe purchase"},
    {"transaction_id": "TXN-1006", "customer_id": "CUST-001", "date": "2026-10-03", "type": "earn", "amount": 15000, "points": 450, "description": "Travel booking"},
    {"transaction_id": "TXN-1007", "customer_id": "CUST-002", "date": "2026-06-11", "type": "earn", "amount": 4500, "points": 45, "description": "Clothing purchase"},
    {"transaction_id": "TXN-1008", "customer_id": "CUST-002", "date": "2026-07-23", "type": "earn", "amount": 9900, "points": 99, "description": "Electronics purchase"},
    {"transaction_id": "TXN-1009", "customer_id": "CUST-002", "date": "2026-08-30", "type": "redeem", "amount": 0, "points": -500, "description": "Redeemed RWD-001"},
    {"transaction_id": "TXN-1010", "customer_id": "CUST-002", "date": "2026-09-21", "type": "earn", "amount": 2750, "points": 27, "description": "Grocery purchase"},
    {"transaction_id": "TXN-1011", "customer_id": "CUST-003", "date": "2026-09-02", "type": "earn", "amount": 6000, "points": 60, "description": "Welcome purchase"},
    {"transaction_id": "TXN-1012", "customer_id": "CUST-003", "date": "2026-09-25", "type": "earn", "amount": 5000, "points": 50, "description": "Grocery purchase"},
    {"transaction_id": "TXN-1013", "customer_id": "CUST-003", "date": "2026-10-08", "type": "earn", "amount": 7000, "points": 70, "description": "Pharmacy purchase"},
    {"transaction_id": "TXN-1014", "customer_id": "CUST-001", "date": "2026-10-11", "type": "earn", "amount": 1800, "points": 54, "description": "Cafe purchase"},
]
# CUST-004 has no transactions on purpose, to show an empty history.


REWARD_CATEGORIES = ["voucher", "merchandise", "experience"]

# DEMO ASSUMPTION: a reward is eligible when the customer has enough points,
# meets the minimum tier, and the reward is in stock.
REWARDS = {
    "RWD-001": {"reward_id": "RWD-001", "name": "Coffee voucher", "category": "voucher", "points_cost": 150, "min_tier": "Bronze", "in_stock": True},
    "RWD-002": {"reward_id": "RWD-002", "name": "Grocery voucher 500 CU", "category": "voucher", "points_cost": 500, "min_tier": "Bronze", "in_stock": True},
    "RWD-003": {"reward_id": "RWD-003", "name": "Branded water bottle", "category": "merchandise", "points_cost": 800, "min_tier": "Silver", "in_stock": True},
    "RWD-004": {"reward_id": "RWD-004", "name": "Wireless earbuds", "category": "merchandise", "points_cost": 3000, "min_tier": "Silver", "in_stock": True},
    "RWD-005": {"reward_id": "RWD-005", "name": "Airport lounge pass", "category": "experience", "points_cost": 2500, "min_tier": "Gold", "in_stock": True},
    "RWD-006": {"reward_id": "RWD-006", "name": "Cooking class for two", "category": "experience", "points_cost": 1200, "min_tier": "Silver", "in_stock": False},
}


CAMPAIGNS = {
    "CMP-001": {
        "campaign_id": "CMP-001",
        "name": "Summer Double Points",
        "status": "completed",
        "start_date": "2026-06-01",
        "end_date": "2026-08-31",
        "scheme_id": "SCH-STANDARD",
        "customers_targeted": 12000,
        "customers_participated": 2760,
        "points_issued": 184000,
        "points_redeemed": 61000,
        "incremental_revenue": 920000,
        "cost": 230000,
    },
    "CMP-002": {
        "campaign_id": "CMP-002",
        "name": "Weekend Booster Launch",
        "status": "active",
        "start_date": "2026-09-01",
        "end_date": "2026-12-31",
        "scheme_id": "SCH-WEEKEND",
        "customers_targeted": 8000,
        "customers_participated": 1040,
        "points_issued": 52000,
        "points_redeemed": 9000,
        "incremental_revenue": 310000,
        "cost": 95000,
    },
    "CMP-003": {
        "campaign_id": "CMP-003",
        "name": "Gold Tier Welcome",
        "status": "scheduled",
        "start_date": "2026-11-01",
        "end_date": "2027-01-31",
        "scheme_id": "SCH-GOLD",
        "customers_targeted": 1500,
        "customers_participated": 0,
        "points_issued": 0,
        "points_redeemed": 0,
        "incremental_revenue": 0,
        "cost": 0,
    },
}


# In-memory only. Starts empty and resets on every server restart.
REDEMPTION_REQUESTS = []
