"""
Entry point for running the MCP RMM server as a standalone process.
This allows the server to be started with `python -m mcp_rmm.server` or imported as a module.
"""

from auth_mcp_server import mcp

def run():
    """Run the MCP server."""
    mcp.run(transport="stdio")
if __name__ == "__main__":
    run()