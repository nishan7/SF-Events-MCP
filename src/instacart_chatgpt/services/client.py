import asyncio
from pprint import pprint

from fastmcp import Client
from fastmcp.client.client import CallToolResult
import json
from src.instacart_chatgpt.services.fastmcp_rec_events import mcp

config = {
    "mcpServers": {
        "SF Events": {
            "url": "https://synthia-unhunted-unctuousnessly.ngrok-free.dev/mcp"
        }
    }
}

client = Client(config)


async def main():
    async with client:
        result: CallToolResult = await client.call_tool(
            name="search_sf_events",
        )
    print('res')
    response = json.loads(result.content[0].text)
    pprint(response)


asyncio.run(main())
