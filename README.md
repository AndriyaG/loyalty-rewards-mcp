# Loyalty Rewards MCP Server

A local-only portfolio demo: an MCP server for a loyalty platform (admin portal
and customer mobile app), plus an agent client that connects to it.

All data is fabricated. There is no hosting, database, authentication or real
customer data.

Status: the server exposes 8 tools over stdio. The agent client is still a stub.

## Project layout

- `server.py` - FastMCP server with the 8 tools (stdio transport, logs to stderr)
- `loyalty_data.py` - fabricated demo data
- `agent_client.py` - agent client stub (lists the server's tools)
- `tests/` - pytest tests
- `.env.example` - placeholder for `GROQ_API_KEY`

## Setup (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

Copy `.env.example` to `.env` and put your own key there (only needed once the
agent is implemented).

## Verify

```powershell
python -c "import fastmcp; print(fastmcp.__version__)"   # 4.1.0
python -m pytest -v
python agent_client.py                                     # Server exposes 8 tools
python server.py                                           # waits on stdio; Ctrl+C to stop
```

### MCP Inspector

Inspector 0.16.0 and later need Node 22.7.5+. On Node 18, use the pinned
older version:

```powershell
npx @modelcontextprotocol/inspector@0.15.0 python server.py
```

With Node 22+ installed, the latest version works too:

```powershell
npx @modelcontextprotocol/inspector python server.py
```

In the Inspector UI choose Transport `STDIO`, Command `python`, Args
`server.py`, then click Connect.

## Tools

| Tool | Parameters |
| --- | --- |
| `get_customer_summary` | `customer_id` |
| `get_transaction_history` | `customer_id`, `limit` (1 to 20, default 5) |
| `list_reward_catalog` | `category` (optional; empty means all) |
| `get_eligible_rewards` | `customer_id` |
| `list_active_schemes` | none |
| `calculate_points_for_purchase` | `purchase_amount`, `scheme_id` |
| `get_campaign_performance` | `campaign_id` (optional; empty means all) |
| `create_redemption_request` | `customer_id`, `reward_id` |

Optional parameters default to an empty string rather than `null`, so their
JSON schema stays a plain `string`. Some LLM tool-calling APIs handle
`anyOf`/nullable schemas badly.

Errors (unknown IDs, a limit out of range, zero or negative amounts, inactive
schemes, insufficient points, wrong tier, out of stock) come back as MCP tool
errors with a plain-English message.

## Demo IDs

- Customers: `CUST-001` (Gold, 4200 pts), `CUST-002` (Silver, 1350 pts),
  `CUST-003` (Bronze, 180 pts), `CUST-004` (Silver, 0 pts, no history)
- Schemes: `SCH-STANDARD`, `SCH-GOLD`, `SCH-WEEKEND`, `SCH-LEGACY` (inactive)
- Rewards: `RWD-001` to `RWD-006` (`RWD-006` is out of stock)
- Campaigns: `CMP-001` (completed), `CMP-002` (active), `CMP-003` (scheduled)

## Demo assumptions

Every rule below is invented for this demo.

- Currency is a generic "currency unit" (`CU`).
- Tiers rank Bronze < Silver < Gold.
- Points are earned per full block of spend, rounded down, and each scheme
  sets its own rate: `points = floor(amount / block_size) * points_per_block`.
  Example: `SCH-STANDARD` gives 1 point per 100 CU, so 1250 CU earns 12 points.
  Purchases below a scheme's `min_purchase` earn 0.
- A reward is eligible when the customer has enough points, meets the minimum
  tier, and the reward is in stock.
- A customer's points balance includes points from before their recorded
  transaction history.
- Campaign metrics are simplified: participation = participated / targeted,
  redemption rate = points redeemed / points issued, ROI = (revenue - cost) / cost.
- `create_redemption_request` is simulated. It creates a `PENDING` request with
  an ID like `REQ-0001` in memory. It never deducts points, takes payment or
  calls any external service. Pending requests do not reserve points.
  **All redemption requests are lost when the server restarts.**
