"""Protocol-level tests: talk to the server over MCP using the fastmcp Client.

`Client(mcp)` connects to the server object in memory (no subprocess, no
network), so this exercises the real MCP list_tools / call_tool path.
"""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from server import mcp

# One valid sample call per tool. Must cover exactly the advertised tools.
SAMPLE_CALLS = {
    "get_customer_summary": {"customer_id": "CUST-001"},
    "get_transaction_history": {"customer_id": "CUST-001", "limit": 2},
    "list_reward_catalog": {"category": "voucher"},
    "get_eligible_rewards": {"customer_id": "CUST-002"},
    "list_active_schemes": {},
    "calculate_points_for_purchase": {"purchase_amount": 1250, "scheme_id": "SCH-STANDARD"},
    "get_campaign_performance": {"campaign_id": "CMP-001"},
    "create_redemption_request": {"customer_id": "CUST-002", "reward_id": "RWD-001"},
}


@pytest.mark.asyncio
async def test_exactly_eight_tools_are_advertised():
    async with Client(mcp) as client:
        assert client.server_info.name == "Loyalty Rewards MCP"
        tools = await client.list_tools()

    names = [t.name for t in tools]
    assert len(names) == 8
    assert set(names) == set(SAMPLE_CALLS)


@pytest.mark.asyncio
async def test_every_tool_has_description_and_object_schemas():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    for tool in tools:
        assert tool.description, f"{tool.name} has no description"
        assert tool.input_schema["type"] == "object"
        assert tool.output_schema["type"] == "object"
        for name, prop in tool.input_schema.get("properties", {}).items():
            assert "anyOf" not in prop, f"{tool.name}.{name} uses a complex schema"
            assert prop.get("description"), f"{tool.name}.{name} has no description"


@pytest.mark.asyncio
async def test_every_advertised_tool_is_callable():
    async with Client(mcp) as client:
        tools = await client.list_tools()
        for tool in tools:
            result = await client.call_tool(tool.name, SAMPLE_CALLS[tool.name])
            assert not result.is_error, tool.name
            assert isinstance(result.structured_content, dict), tool.name
            assert result.structured_content, tool.name


@pytest.mark.asyncio
async def test_only_redemption_tool_is_not_read_only():
    async with Client(mcp) as client:
        tools = await client.list_tools()

    read_only = {t.name: t.annotations.read_only_hint for t in tools}
    assert read_only.pop("create_redemption_request") is False
    assert all(read_only.values())


@pytest.mark.asyncio
async def test_tool_errors_reach_the_client_with_clear_messages():
    async with Client(mcp) as client:
        with pytest.raises(ToolError, match="Unknown customer_id 'CUST-999'"):
            await client.call_tool("get_customer_summary", {"customer_id": "CUST-999"})

        result = await client.call_tool(
            "create_redemption_request",
            {"customer_id": "CUST-003", "reward_id": "RWD-002"},
            raise_on_error=False,
        )
    assert result.is_error
    assert "insufficient points" in result.content[0].text


@pytest.mark.asyncio
async def test_wrong_argument_types_are_rejected():
    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("get_transaction_history", {"customer_id": "CUST-001", "limit": "lots"})
        with pytest.raises(ToolError):
            await client.call_tool("calculate_points_for_purchase", {"scheme_id": "SCH-STANDARD"})
