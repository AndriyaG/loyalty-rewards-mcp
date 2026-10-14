"""Loyalty Rewards Assistant: a terminal chat agent for the Loyalty Rewards MCP server.

How one question is answered:
1. The conversation and the MCP tools (converted to Groq's function format)
   are sent to Groq.
2. If Groq asks for tool calls, each one is run through the MCP client and the
   result is appended as a "tool" message.
3. Steps 1-2 repeat until Groq replies without tool calls (the final answer),
   up to MAX_ITERATIONS Groq calls per question.

Tool names, descriptions and schemas are discovered from server.py at runtime;
nothing is duplicated here. create_redemption_request always needs a typed
"yes" in this terminal before it runs, whatever the model says.

Run: python agent_client.py   (needs GROQ_API_KEY and GROQ_MODEL in .env)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import groq
from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

ASSISTANT_NAME = "Loyalty Rewards Assistant"
SERVER_PATH = Path(__file__).parent / "server.py"
SERVER_LOG = Path(__file__).parent / "server.log"

MAX_ITERATIONS = 6
MAX_COMPLETION_TOKENS = 1024
MAX_TOOL_OUTPUT_CHARS = 4000
CONFIRMATION_REQUIRED = {"create_redemption_request"}
SUGGESTED_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = f"""You are the {ASSISTANT_NAME} for a demo loyalty platform \
(admin portal and customer mobile app).
- Always use the tools for customer balances, transaction history, reward \
eligibility, earn schemes, point calculations and campaign metrics.
- Never invent customers, points, rewards, schemes or campaign numbers. If you \
need an ID you do not have, ask the user. If a tool returns an error, explain it plainly.
- Redemption is simulated: create_redemption_request only creates a PENDING \
request. It does not deduct points, take payment or ship anything. Say so.
- If the user declines a redemption, do not try it again unless they ask.
- All data is fabricated demo data. Amounts are in generic currency units (CU).
- Keep answers short and clear."""


class AgentError(Exception):
    """A problem to show the user. If fatal is True the chat ends."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


# ---------- MCP <-> Groq conversion ----------

def mcp_tools_to_groq(tools) -> list[dict]:
    """Turn MCP tool definitions into Groq's function-calling format."""
    groq_tools = []
    for tool in tools:
        groq_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.input_schema or {"type": "object", "properties": {}},
            },
        })
    return groq_tools


def parse_tool_arguments(raw: str | None) -> dict:
    """Parse the model's arguments string as JSON. Raises ValueError if invalid.

    Only json.loads is used: model output is treated as data, never as code.
    """
    if raw is None or not raw.strip():
        return {}
    arguments = json.loads(raw)
    if not isinstance(arguments, dict):
        raise ValueError("arguments must be a JSON object")
    return arguments


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [truncated {len(text) - limit} characters]"


def tool_result_to_text(result) -> str:
    texts = [block.text for block in result.content if hasattr(block, "text")]
    if result.is_error:
        return json.dumps({"error": " ".join(texts) or "The tool failed."})
    if result.structured_content is not None:
        return json.dumps(result.structured_content)
    return " ".join(texts)


def assistant_message_to_dict(message) -> dict:
    entry = {"role": "assistant"}
    if message.content:
        entry["content"] = message.content
    if message.tool_calls:
        entry["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ]
    return entry


# ---------- tool execution ----------

def ask_confirmation(tool_name: str, arguments: dict) -> bool:
    print(f"\n  The assistant wants to call {tool_name} with:")
    print("  " + json.dumps(arguments, indent=2).replace("\n", "\n  "))
    print("  This creates a SIMULATED pending request. No points are deducted.")
    answer = input('  Type "yes" to allow it, anything else to cancel: ')
    return answer.strip().lower() == "yes"


async def execute_tool_call(mcp_client, tool_call, known_tool_names, confirm=ask_confirmation) -> str:
    """Run one tool call from the model and return the text for the tool message."""
    name = tool_call.function.name
    if name not in known_tool_names:
        print(f"  [tool] rejected unknown tool '{name}'")
        return json.dumps({"error": f"Unknown tool '{name}'. Available tools: {', '.join(sorted(known_tool_names))}."})

    try:
        arguments = parse_tool_arguments(tool_call.function.arguments)
    except ValueError as error:
        print(f"  [tool] rejected {name}: arguments were not valid JSON")
        return json.dumps({"error": f"Invalid arguments for {name}: {error}. Send a JSON object."})

    if name in CONFIRMATION_REQUIRED and not confirm(name, arguments):
        print("  Cancelled. The tool was not called.")
        return json.dumps({
            "status": "declined",
            "message": "The user declined, so the tool was NOT called and no request "
            "was created. Do not retry unless the user asks again.",
        })

    print(f"  [tool] {name}({json.dumps(arguments)})")
    result = await mcp_client.call_tool(name, arguments, raise_on_error=False)
    if result.is_error:
        print(f"  [tool] {name} returned an error")
    return truncate(tool_result_to_text(result), MAX_TOOL_OUTPUT_CHARS)


# ---------- Groq calls and errors ----------

def _error_details(error) -> dict:
    body = getattr(error, "body", None)
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return body["error"]
    return {}


def describe_groq_error(error, model: str) -> AgentError:
    """Turn a Groq SDK exception into a readable message. Never includes the API key."""
    details = _error_details(error)
    code = details.get("code")
    text = str(details.get("message", "")).lower()

    if isinstance(error, groq.APIConnectionError):
        return AgentError("Could not reach Groq. Check your internet connection and try again.")
    if isinstance(error, groq.AuthenticationError):
        return AgentError("Groq rejected the API key (401). Check GROQ_API_KEY in your .env file.", fatal=True)
    if isinstance(error, groq.PermissionDeniedError):
        return AgentError("Groq denied access (403). Check that your key can use this model.", fatal=True)
    if isinstance(error, groq.RateLimitError):
        wait = error.response.headers.get("retry-after")
        hint = f"Wait about {wait} seconds" if wait else "Wait a minute"
        return AgentError(f"Groq rate limit reached (429). {hint} and try again.")
    model_problem = (
        isinstance(error, groq.NotFoundError)
        or code in {"model_not_found", "model_decommissioned"}
        or ("tool" in text and "support" in text)
    )
    if model_problem:
        return AgentError(
            f"Model '{model}' is unavailable or does not support tool calling. "
            f"Change GROQ_MODEL in .env, for example GROQ_MODEL={SUGGESTED_MODEL}.",
            fatal=True,
        )
    if isinstance(error, groq.APIStatusError):
        return AgentError(f"Groq returned an error ({error.status_code}): {details.get('message', 'no details')}")
    return AgentError(f"Unexpected Groq error: {type(error).__name__}")


async def run_turn(groq_client, mcp_client, model, messages, groq_tools, known_tool_names,
                   confirm=ask_confirmation) -> str:
    """Answer the latest user message. Appends to `messages` and returns the final answer."""
    retried_malformed_call = False

    for _ in range(MAX_ITERATIONS):
        try:
            response = await groq_client.chat.completions.create(
                model=model,
                messages=messages,
                tools=groq_tools,
                tool_choice="auto",
                max_completion_tokens=MAX_COMPLETION_TOKENS,
                temperature=0.2,
            )
        except groq.BadRequestError as error:
            if _error_details(error).get("code") != "tool_use_failed":
                raise describe_groq_error(error, model) from None
            if retried_malformed_call:
                raise AgentError("The model sent a malformed tool call twice. Try rephrasing your question.") from None
            retried_malformed_call = True
            print("  The model sent a malformed tool call. Retrying once...")
            continue
        except groq.GroqError as error:
            raise describe_groq_error(error, model) from None

        choice = response.choices[0]
        message = choice.message
        messages.append(assistant_message_to_dict(message))

        if not message.tool_calls:
            answer = message.content or "(The model returned an empty answer.)"
            if choice.finish_reason == "length":
                answer += "\n[Answer cut off at the token limit.]"
            return answer

        for tool_call in message.tool_calls:
            content = await execute_tool_call(mcp_client, tool_call, known_tool_names, confirm)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_call.function.name,
                "content": content,
            })

    raise AgentError(f"Stopped after {MAX_ITERATIONS} steps without a final answer. Try a more specific question.")


# ---------- terminal chat ----------

async def chat_loop(groq_client, mcp_client, model) -> int:
    tools = await mcp_client.list_tools()
    groq_tools = mcp_tools_to_groq(tools)
    known_tool_names = {tool.name for tool in tools}

    print(f"{ASSISTANT_NAME} (model: {model}, {len(tools)} tools from {SERVER_PATH.name})")
    print("Ask about customers, rewards, schemes or campaigns, e.g. 'What can CUST-002 redeem?'")
    print('All data is fabricated. Redemptions are simulated. Type "exit" or press Ctrl+C to quit.\n')

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    while True:
        try:
            question = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            return 0
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            print("Goodbye.")
            return 0

        turn_start = len(messages)
        messages.append({"role": "user", "content": question})
        try:
            answer = await run_turn(groq_client, mcp_client, model, messages, groq_tools, known_tool_names)
        except AgentError as error:
            del messages[turn_start:]
            print(f"\n[!] {error}\n")
            if error.fatal:
                return 1
            continue
        except Exception as error:
            del messages[turn_start:]
            print(f"\n[!] Something went wrong: {type(error).__name__}: {error}\n")
            continue
        print(f"\nAssistant: {answer}\n")


async def main() -> int:
    load_dotenv()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    model = os.environ.get("GROQ_MODEL", "").strip()
    if not api_key:
        print("GROQ_API_KEY is not set. Copy .env.example to .env and add your key.")
        return 1
    if not model:
        print(f"GROQ_MODEL is not set. Add it to .env, for example GROQ_MODEL={SUGGESTED_MODEL}")
        return 1

    groq_client = groq.AsyncGroq(api_key=api_key)

    connected = False
    try:
        # Server stderr goes to server.log so its logs don't clutter the chat.
        transport = PythonStdioTransport(SERVER_PATH, log_file=SERVER_LOG)
        async with Client(transport) as mcp_client:
            connected = True
            return await chat_loop(groq_client, mcp_client, model)
    except Exception as error:
        if connected:
            raise
        print(f"Could not start the MCP server ({SERVER_PATH.name}): {type(error).__name__}: {error}")
        print(f"Check {SERVER_LOG.name}, or run 'python {SERVER_PATH.name}' to see the server's error.")
        return 1


if __name__ == "__main__":
    # Windows consoles often use cp1252, which can't encode some characters models emit.
    sys.stdout.reconfigure(errors="replace")
    try:
        exit_code = asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye.")
        exit_code = 0
    sys.exit(exit_code)
