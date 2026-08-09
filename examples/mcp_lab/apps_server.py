"""
Lab server: MCP Apps (the io.modelcontextprotocol/ui extension).

A tool can carry an HTML app that the host renders inline. The tool is
annotated with a `resource_uri`; the host reads that `ui://` resource and
renders it in a sandbox. Exercises the extension end to end: negotiation,
the `_meta.ui.resourceUri` annotation, and the app resource itself.

Run standalone (stdio):
    python examples/mcp_lab/apps_server.py
"""

import sys

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer

DICE_APP = """<!doctype html>
<meta charset="utf-8">
<style>
  body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 0; padding: 16px;
         color: #e5e5e5; background: #171717; }
  .face { font-size: 56px; line-height: 1; margin: 8px 0; }
  button { font: inherit; padding: 6px 12px; border-radius: 6px; cursor: pointer;
           border: 1px solid #404040; background: #262626; color: #e5e5e5; }
  button:hover { background: #333; }
  .hint { color: #a3a3a3; font-size: 12px; margin-top: 10px; }
</style>
<div class="face" id="face">?</div>
<button id="roll">Roll</button>
<div class="hint">Rendered by the server, sandboxed by the host.</div>
<script>
  const faces = ["\\u2680","\\u2681","\\u2682","\\u2683","\\u2684","\\u2685"];
  document.getElementById("roll").onclick = () => {
    const n = Math.floor(Math.random() * 6);
    document.getElementById("face").textContent = faces[n];
  };
</script>
"""

apps = Apps()


@apps.tool(
    resource_uri="ui://dice/app.html",
    description="Roll a die and return the value, with a rollable UI panel.",
)
def roll_die(sides: int = 6) -> int:
    """Roll a die with the given number of sides."""
    # Deterministic so the lab server stays reproducible; the app panel is
    # where the interactive rolling happens.
    return max(1, min(sides, 4))


apps.add_html_resource(
    "ui://dice/app.html",
    DICE_APP,
    name="dice-panel",
    title="Dice",
    description="A small interactive dice panel served by the MCP server.",
)

server = MCPServer(
    "pico-lab-apps",
    instructions="Lab server exposing an MCP App (interactive HTML UI) alongside a tool.",
    extensions=[apps],
)


if __name__ == "__main__":
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
        server.run("streamable-http", port=port)
    else:
        server.run("stdio")
