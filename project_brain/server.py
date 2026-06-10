"""MCP stdio server entry point."""

from __future__ import annotations

import asyncio
import os

from project_brain.brain.manager import BrainManager
from project_brain.tools.registry import ToolRegistry, create_registry


SERVER_NAME = "project-brain"


def build_server(registry: ToolRegistry):
    """Build an MCP low-level server for stdio transport."""

    from mcp.server import Server

    app = Server(SERVER_NAME)

    @app.list_tools()
    async def list_tools():
        return registry.list_mcp_tools()

    @app.call_tool()
    async def call_tool(name: str, arguments: dict):
        return await registry.execute(name, arguments)

    return app


async def run_server(brain_path: str | None = None) -> None:
    """Run the stdio MCP server with a loaded PROJECT_BRAIN.json."""

    from mcp.server.stdio import stdio_server

    manager = BrainManager(brain_path or os.environ.get("BRAIN_PATH", "PROJECT_BRAIN.json"))
    registry = create_registry(manager.load())
    app = build_server(registry)
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def main() -> None:
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
