"""Offline tests for agent_client.py.

Groq is replaced by a fake client that replays scripted responses, and the MCP
server runs in memory, so no network access or API key is needed.
"""

import json
from types import SimpleNamespace

import groq
import httpx
import pytest
from fastmcp import Client

import agent_client
import loyalty_data as data
from agent_client import (
    AgentError,
    describe_groq_error,
    execute_tool_call,
    mcp_tools_to_groq,
    parse_tool_arguments,
    run_turn,
    truncate,
)
from server import mcp

MODEL = "fake-model"


# ---------- fakes ----------

def tool_call(name, arguments, call_id="call_1"):
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return SimpleNamespace(id=call_id, type="function", function=SimpleNamespace(name=name, arguments=raw))


def reply(content=None, tool_calls=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])


def groq_error(error_class, status, body=None, headers=None):
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status, request=request, headers=headers or {})
    return error_class(f"Error code: {status}", response=response, body=body)


class FakeGroq:
    """Mimics groq.AsyncGroq().chat.completions.create with scripted results."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


async def run(script, question="hi", confirm=lambda name, args: False):
    fake = FakeGroq(script)
    async with Client(mcp) as mcp_client:
        tools = await mcp_client.list_tools()
        messages = [{"role": "system", "content": "test"}, {"role": "user", "content": question}]
        answer = await run_turn(
            fake, mcp_client, MODEL, messages, mcp_tools_to_groq(tools), {t.name for t in tools}, confirm
        )
    return answer, messages, fake


def tool_messages(messages):
    return [m for m in messages if m["role"] == "tool"]


# ---------- conversion and parsing ----------

@pytest.mark.asyncio
async def test_tools_are_converted_from_mcp_schemas_without_duplication():
    async with Client(mcp) as client:
        tools = await client.list_tools()
    groq_tools = mcp_tools_to_groq(tools)

    assert len(groq_tools) == 8
    for tool, converted in zip(tools, groq_tools):
        assert converted["type"] == "function"
        assert converted["function"]["name"] == tool.name
        assert converted["function"]["description"] == tool.description
        assert converted["function"]["parameters"] == tool.input_schema


def test_parse_arguments_valid_and_empty():
    assert parse_tool_arguments('{"customer_id": "CUST-001"}') == {"customer_id": "CUST-001"}
    assert parse_tool_arguments("") == {}
    assert parse_tool_arguments(None) == {}


@pytest.mark.parametrize("raw", ["{bad json", "[1, 2]", '"text"', "__import__('os').system('echo hi')"])
def test_parse_arguments_rejects_non_objects_and_code(raw):
    with pytest.raises(ValueError):
        parse_tool_arguments(raw)


def test_truncate():
    assert truncate("short", 10) == "short"
    assert truncate("x" * 25, 10) == "x" * 10 + "... [truncated 15 characters]"


# ---------- agent loop ----------

@pytest.mark.asyncio
async def test_question_to_tool_call_to_final_answer():
    answer, messages, fake = await run([
        reply(tool_calls=[tool_call("get_customer_summary", {"customer_id": "CUST-001"})]),
        reply(content="Asha Demo has 4200 points."),
    ])

    assert answer == "Asha Demo has 4200 points."
    assert len(fake.requests) == 2
    first = fake.requests[0]
    assert first["max_completion_tokens"] == agent_client.MAX_COMPLETION_TOKENS
    assert len(first["tools"]) == 8

    [tool_message] = tool_messages(messages)
    assert tool_message["tool_call_id"] == "call_1"
    assert json.loads(tool_message["content"])["points_balance"] == 4200
    assert fake.requests[1]["messages"][-1] == tool_message


@pytest.mark.asyncio
async def test_redemption_declined_is_not_executed():
    answer, messages, _ = await run(
        [
            reply(tool_calls=[tool_call("create_redemption_request", {"customer_id": "CUST-002", "reward_id": "RWD-001"})]),
            reply(content="OK, I did not create it."),
        ],
        confirm=lambda name, args: False,
    )
    assert data.REDEMPTION_REQUESTS == []
    assert json.loads(tool_messages(messages)[0]["content"])["status"] == "declined"
    assert answer == "OK, I did not create it."


@pytest.mark.asyncio
async def test_redemption_confirmed_is_executed_once():
    seen = []

    def confirm(name, args):
        seen.append((name, args))
        return True

    await run(
        [
            reply(tool_calls=[tool_call("create_redemption_request", {"customer_id": "CUST-002", "reward_id": "RWD-001"})]),
            reply(content="Created REQ-0001."),
        ],
        confirm=confirm,
    )
    assert seen == [("create_redemption_request", {"customer_id": "CUST-002", "reward_id": "RWD-001"})]
    assert len(data.REDEMPTION_REQUESTS) == 1
    assert data.REDEMPTION_REQUESTS[0]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_read_only_tools_do_not_ask_for_confirmation():
    def confirm(name, args):
        raise AssertionError("confirmation should not be requested")

    await run(
        [reply(tool_calls=[tool_call("list_active_schemes", {})]), reply(content="3 schemes.")],
        confirm=confirm,
    )


@pytest.mark.asyncio
async def test_unknown_tool_name_is_rejected():
    _, messages, _ = await run([
        reply(tool_calls=[tool_call("delete_all_customers", {})]),
        reply(content="Sorry."),
    ])
    assert "Unknown tool 'delete_all_customers'" in tool_messages(messages)[0]["content"]


@pytest.mark.asyncio
async def test_invalid_json_arguments_are_reported_to_the_model():
    _, messages, _ = await run([
        reply(tool_calls=[tool_call("get_customer_summary", "{customer_id: CUST-001")]),
        reply(content="Let me fix that."),
    ])
    assert "Invalid arguments" in tool_messages(messages)[0]["content"]


@pytest.mark.asyncio
async def test_invalid_argument_values_return_server_error():
    _, messages, _ = await run([
        reply(tool_calls=[tool_call("get_transaction_history", {"customer_id": "CUST-001", "limit": 0})]),
        reply(content="The limit must be 1 to 20."),
    ])
    content = json.loads(tool_messages(messages)[0]["content"])
    assert "limit must be between 1 and 20" in content["error"]


@pytest.mark.asyncio
async def test_large_tool_output_is_truncated(monkeypatch):
    monkeypatch.setattr(agent_client, "MAX_TOOL_OUTPUT_CHARS", 50)
    _, messages, _ = await run([
        reply(tool_calls=[tool_call("list_reward_catalog", {})]),
        reply(content="Here is the catalog."),
    ])
    content = tool_messages(messages)[0]["content"]
    assert content.startswith('{"category": "all"')
    assert "[truncated" in content


@pytest.mark.asyncio
async def test_malformed_tool_call_is_retried_once():
    malformed = groq_error(groq.BadRequestError, 400, {"error": {"code": "tool_use_failed", "message": "Failed to call a function."}})
    answer, _, fake = await run([malformed, reply(content="Recovered.")])
    assert answer == "Recovered."
    assert len(fake.requests) == 2


@pytest.mark.asyncio
async def test_malformed_tool_call_twice_gives_up():
    body = {"error": {"code": "tool_use_failed", "message": "Failed to call a function."}}
    with pytest.raises(AgentError, match="malformed tool call twice"):
        await run([groq_error(groq.BadRequestError, 400, body), groq_error(groq.BadRequestError, 400, body)])


@pytest.mark.asyncio
async def test_iteration_cap():
    script = [reply(tool_calls=[tool_call("list_active_schemes", {})]) for _ in range(10)]
    with pytest.raises(AgentError, match="Stopped after 6 steps"):
        await run(script)


# ---------- readable Groq errors ----------

def test_auth_error_is_fatal_and_mentions_env_var():
    error = describe_groq_error(groq_error(groq.AuthenticationError, 401, {"error": {"message": "Invalid API Key"}}), MODEL)
    assert error.fatal
    assert "GROQ_API_KEY" in str(error)


def test_rate_limit_suggests_waiting():
    error = describe_groq_error(groq_error(groq.RateLimitError, 429, {"error": {}}, {"retry-after": "12"}), MODEL)
    assert not error.fatal
    assert "429" in str(error) and "12 seconds" in str(error)


@pytest.mark.parametrize(
    "error_class, status, body",
    [
        (groq.NotFoundError, 404, {"error": {"code": "model_not_found", "message": "The model does not exist"}}),
        (groq.BadRequestError, 400, {"error": {"code": "model_decommissioned", "message": "decommissioned"}}),
        (groq.BadRequestError, 400, {"error": {"message": "This model does not support tool use"}}),
    ],
)
def test_model_problems_suggest_changing_groq_model(error_class, status, body):
    error = describe_groq_error(groq_error(error_class, status, body), MODEL)
    assert error.fatal
    assert "GROQ_MODEL" in str(error) and MODEL in str(error)


@pytest.mark.asyncio
async def test_groq_error_during_turn_becomes_agent_error():
    with pytest.raises(AgentError, match="429"):
        await run([groq_error(groq.RateLimitError, 429, {"error": {}})])


@pytest.mark.asyncio
async def test_execute_tool_call_never_runs_unknown_tools():
    async with Client(mcp) as client:
        content = await execute_tool_call(client, tool_call("os.system", "{}"), {"list_active_schemes"})
    assert "Unknown tool" in content
