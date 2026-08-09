"""
Demo MCP servers shipped with the playground.

Each exercises one part of the 2026-07-28 spec and is offered as a one-click
preset in the WebUI. They live inside the package (not in examples/) so that
`pip install picoagents` gets working presets, not an empty playground.

Run any of them standalone:
    python -m picoagents.webui.mcp.servers.basic_server
"""

from pathlib import Path

SERVERS_DIR = Path(__file__).parent

__all__ = ["SERVERS_DIR"]
