"""Agent client stub for the Loyalty Rewards MCP server.

For now this only starts server.py over stdio and lists its tools.
The Groq-powered agent loop will be added in a later step.
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from fastmcp import Client

SERVER_PATH = Path(__file__).parent / "server.py"


async def main() -> None:
    load_dotenv()
    if os.environ.get("GROQ_API_KEY"):
        print("GROQ_API_KEY is set.")
    else:
        print("GROQ_API_KEY is not set (not needed yet; see .env.example).")

    async with Client(SERVER_PATH) as client:
        tools = await client.list_tools()
        print(f"Server exposes {len(tools)} tools")
        for tool in tools:
            print(f"- {tool.name}")

    # TODO: send the user's question plus these tools to Groq and run tool calls.


if __name__ == "__main__":
    asyncio.run(main())
