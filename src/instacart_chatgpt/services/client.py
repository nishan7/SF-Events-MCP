import asyncio
from pprint import pprint

from fastmcp import Client
from fastmcp.client.client import CallToolResult
import json
from src.instacart_chatgpt.services.fastmcp_rec_events import mcp

config = {
    "mcpServers": {
        "sf-rec-events": {
            "url": "http://localhost:8000/mcp"
        }
    }
}

client = Client(config)


async def main():
    async with client:
        result: CallToolResult = await client.call_tool(
            name="fetch_rec_events",
        )
    print('res')
    response = json.loads(result.content[0].text)
    pprint(response)


asyncio.run(main())
