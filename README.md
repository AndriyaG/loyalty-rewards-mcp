# Loyalty Rewards MCP Server

A local-only portfolio demo: an [MCP](https://modelcontextprotocol.io) server
for a loyalty platform (admin portal and customer mobile app), plus a terminal
chat agent that answers questions by calling the server's tools through Groq.

> **Demo only.**
> - **All data is fabricated.** Customers, rewards, schemes, campaigns and every
>   business rule are invented. Nothing describes a real person or company.
> - **Everything runs locally.** The server talks over stdio on your machine.
>   There is no hosting, public endpoint, database, authentication or payment.
>   The only network call is the agent's request to the Groq API.
> - **GitHub stores source code only.** Nothing is deployed from this repo, and
>   your `.env` (with your API key) is gitignored and never committed.

## Architecture

```text
  You (terminal)
       |
       v
  agent_client.py  ---- HTTPS (chat + tool definitions) ---->  Groq API
  "Loyalty Rewards  <--- answer or tool calls ---------------  (LLM)
   Assistant"
       |
       |  MCP over stdio (fastmcp Client starts server.py as a subprocess)
       v
  server.py  (FastMCP, 8 tools, logs to stderr -> server.log)
       |
       |  plain Python import
       v
  loyalty_data.py  (fabricated in-memory data; redemption requests reset on restart)
```

The MCP Inspector can connect to `server.py` the same way, in place of the agent.

## Project layout

- `server.py` - FastMCP server with the 8 tools (stdio transport, logs to stderr)
- `loyalty_data.py` - fabricated demo data
- `agent_client.py` - terminal chat agent (Groq SDK + fastmcp `Client`)
- `tests/` - pytest tests (offline; no Groq key needed)
- `.env.example` - placeholders for `GROQ_API_KEY` and `GROQ_MODEL`

## The 8 tools

| Tool | Parameters | What it does |
| --- | --- | --- |
| `get_customer_summary` | `customer_id` | Profile, tier, balance, earn scheme, history totals |
| `get_transaction_history` | `customer_id`, `limit` (1 to 20, default 5) | Recent earn/redeem transactions, newest first |
| `list_reward_catalog` | `category` (optional) | Rewards with cost, minimum tier and stock |
| `get_eligible_rewards` | `customer_id` | What the customer can redeem now, and why not for the rest |
| `list_active_schemes` | none | Active points-earning schemes and their rates |
| `calculate_points_for_purchase` | `purchase_amount`, `scheme_id` | Points a purchase would earn (awards nothing) |
| `get_campaign_performance` | `campaign_id` (optional) | Participation, redemption rate and ROI |
| `create_redemption_request` | `customer_id`, `reward_id` | Creates a **simulated** `PENDING` request |

Seven tools are read-only. `create_redemption_request` only appends to an
in-memory list; it never deducts points or contacts anything.

Optional parameters default to an empty string rather than `null`, so their
JSON schema stays a plain `string` (some LLM tool-calling APIs handle nullable
schemas badly). Errors such as unknown IDs, out-of-range limits, non-positive
amounts, inactive schemes, insufficient points, wrong tier or out of stock come
back as MCP tool errors with a plain-English message.

## Setup (Windows PowerShell)

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```powershell
uv venv --python 3.11
.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
```

On macOS/Linux, activate with `source .venv/bin/activate` instead.

### Create your `.env`

Only the agent needs it; the server, tests and Inspector do not.

```powershell
Copy-Item .env.example .env
```

Then open `.env` and replace the placeholder with your own Groq API key
(from the [Groq console](https://console.groq.com/keys)). Keep `GROQ_MODEL` set
to a model that supports tool use, for example `llama-3.3-70b-versatile`.
`.env` is gitignored; never commit it or paste the key anywhere else.

## Run the tests

```powershell
python -m pytest -v
```

The tests are fully offline: they remove `GROQ_API_KEY` from the environment,
block outbound network access and fake the Groq client.

## Try the server in MCP Inspector

Requires Node.js. Inspector 0.16.0 and later need Node 22.7.5+; on older Node
use the pinned version:

```powershell
npx @modelcontextprotocol/inspector@0.15.0 python server.py   # Node 18+
npx @modelcontextprotocol/inspector python server.py          # Node 22.7.5+
```

In the Inspector UI choose Transport `STDIO`, Command `python`, Args
`server.py`, then click Connect and open the Tools tab. Run it with the venv
activated so `python` has `fastmcp` installed.

You can also start the server directly with `python server.py`. It waits
silently on stdio for an MCP client; press Ctrl+C to stop.

## Run the agent

```powershell
python agent_client.py
```

Type a question, or `exit` (or Ctrl+C) to quit. The server's log output goes to
`server.log` (gitignored).

### Example questions

- "Give me a summary of CUST-001."
- "Show the last 3 transactions for CUST-002."
- "What can CUST-002 redeem right now?"
- "Why can't CUST-003 get the wireless earbuds (RWD-004)?"
- "Which voucher rewards are in the catalog?"
- "How many points does a 1250 CU purchase earn on SCH-WEEKEND?" (50 points)
- "Can I use SCH-LEGACY?" (it is inactive, so the tool returns an error)
- "How is campaign CMP-002 performing?"
- "Redeem RWD-001 for CUST-003." (asks you to type `yes` first)
- "Does CUST-004 have any transactions?" (no, on purpose)

### How a question is answered

1. `agent_client.py` starts `server.py` over stdio with the fastmcp `Client`
   and lists its tools. Each tool's MCP input schema is passed to Groq as a
   function definition, unchanged.
2. Your question, the conversation so far and the tools go to Groq.
3. If Groq replies with tool calls, the client checks each tool name against
   the discovered list, parses the arguments with `json.loads`, runs the tool
   through MCP and sends the result back as a `tool` message (cut to 4000
   characters if larger).
4. Steps 2-3 repeat until Groq answers without tool calls, at most 6 Groq calls
   per question.

`create_redemption_request` is gated in code: the client shows the arguments
and only runs it after you type `yes`. Otherwise the model is told you declined.

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
