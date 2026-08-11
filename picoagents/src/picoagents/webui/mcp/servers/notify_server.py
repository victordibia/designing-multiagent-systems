"""
Lab server: dynamic tool registry / list-changed notifications.

Exercises `subscriptions/listen`: registering or removing a tool at runtime
emits a tools list-changed notification to subscribed clients.

Run standalone (stdio):
    python -m picoagents.webui.mcp.servers.notify_server
"""

import sys

from mcp.server.mcpserver import MCPServer

server = MCPServer(
    "pico-lab-notify",
    instructions="Lab server whose tool list changes at runtime.",
)


@server.tool()
def register_greeter(name: str) -> str:
    """Register a new greeter tool named greet_<name> (fires tools list-changed)."""

    def greeter() -> str:
        return f"Hello from {name}!"

    greeter.__name__ = f"greet_{name}"
    greeter.__doc__ = f"Say hello from {name}."
    server.add_tool(greeter)
    return f"Registered tool greet_{name}"


@server.tool()
def unregister_greeter(name: str) -> str:
    """Remove a previously registered greeter tool (fires tools list-changed)."""
    server.remove_tool(f"greet_{name}")
    return f"Removed tool greet_{name}"


if __name__ == "__main__":
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
        server.run("streamable-http", port=port)
    else:
        server.run("stdio")
