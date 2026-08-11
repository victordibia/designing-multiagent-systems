"""
Lab server: MCP Apps (the io.modelcontextprotocol/ui extension).

A tool carries an interactive HTML app that the host renders in a sandboxed
iframe and talks to over JSON-RPC on postMessage. This server exercises the
whole extension:

- `_meta.ui.resourceUri` annotation on a tool
- the `ui://` app resource itself
- the app calling back into the server with `tools/call` over the bridge

The app is a small sales explorer: switching region or metric inside the
iframe issues a real `tools/call` to `query_sales`, so every interaction
shows up as JSON-RPC traffic in the playground's Wire tab.

Run standalone (stdio):
    python -m picoagents.webui.mcp.servers.apps_server
"""

import sys
from typing import Any, Dict, List

from mcp.server.apps import Apps
from mcp.server.mcpserver import MCPServer

# Deterministic sample data so the lab server is reproducible.
SALES: Dict[str, Dict[str, List[int]]] = {
    "north": {"revenue": [42, 55, 61, 58, 73, 80], "units": [120, 141, 158, 150, 190, 210]},
    "south": {"revenue": [31, 29, 44, 52, 49, 63], "units": [95, 88, 130, 149, 141, 176]},
    "europe": {"revenue": [58, 62, 60, 71, 84, 91], "units": [161, 172, 168, 199, 231, 254]},
}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]

APP_HTML = """<!doctype html>
<meta charset="utf-8">
<style>
  :root { color-scheme: dark; }
  body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; margin: 0;
         padding: 14px; color: #e5e5e5; background: #0a0a0a; }
  .row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
  button { font: inherit; font-size: 12px; padding: 4px 10px; border-radius: 6px;
           border: 1px solid #333; background: #171717; color: #a3a3a3; cursor: pointer; }
  button:hover { background: #222; color: #e5e5e5; }
  button[aria-pressed="true"] { background: #e5e5e5; color: #0a0a0a; border-color: #e5e5e5; }
  .chart { display: flex; align-items: flex-end; gap: 8px; height: 130px;
           padding: 8px 4px; border-bottom: 1px solid #262626; }
  .bar { flex: 1; background: linear-gradient(180deg,#4ade80,#16a34a); border-radius: 3px 3px 0 0;
         position: relative; min-height: 2px; transition: height .25s ease; }
  .bar span { position: absolute; top: -16px; left: 0; right: 0; text-align: center;
              font-size: 10px; color: #a3a3a3; }
  .labels { display: flex; gap: 8px; margin-top: 4px; }
  .labels div { flex: 1; text-align: center; font-size: 10px; color: #737373; }
  .meta { margin-top: 10px; font-size: 11px; color: #737373; }
  .err { color: #f87171; font-size: 12px; }
</style>

<div class="row">
  <strong style="font-size:13px">Sales</strong>
  <span style="flex:1"></span>
  <button data-region="north" aria-pressed="true">North</button>
  <button data-region="south" aria-pressed="false">South</button>
  <button data-region="europe" aria-pressed="false">Europe</button>
</div>
<div class="row">
  <button data-metric="revenue" aria-pressed="true">Revenue</button>
  <button data-metric="units" aria-pressed="false">Units</button>
</div>

<div class="chart" id="chart"></div>
<div class="labels" id="labels"></div>
<div class="meta" id="meta">Connecting to host...</div>

<script>
(() => {
  let nextId = 1;
  const pending = new Map();
  let region = "north", metric = "revenue";

  function send(msg) { parent.postMessage(msg, "*"); }

  function call(method, params) {
    const id = nextId++;
    send({ jsonrpc: "2.0", id, method, params });
    return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  }

  window.addEventListener("message", (e) => {
    const msg = e.data;
    if (!msg || msg.jsonrpc !== "2.0") return;
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : resolve(msg.result);
    }
  });

  function reportSize() {
    send({ jsonrpc: "2.0", method: "ui/notifications/size-changed",
           params: { width: document.body.scrollWidth,
                     height: document.body.scrollHeight + 24 } });
  }

  function render(data) {
    const values = data.values, months = data.months;
    const max = Math.max(...values, 1);
    document.getElementById("chart").innerHTML = values
      .map(v => `<div class="bar" style="height:${(v / max) * 100}%"><span>${v}</span></div>`)
      .join("");
    document.getElementById("labels").innerHTML = months
      .map(m => `<div>${m}</div>`).join("");
    document.getElementById("meta").textContent =
      `${data.region} - ${data.metric} - total ${data.total} (fetched over the app bridge)`;
    reportSize();
  }

  async function refresh() {
    document.getElementById("meta").textContent = "Calling query_sales...";
    try {
      const res = await call("tools/call",
        { name: "query_sales", arguments: { region, metric } });
      const sc = res.structuredContent || res.structured_content || {};
      render(sc.result || sc);
    } catch (err) {
      document.getElementById("meta").innerHTML =
        `<span class="err">${err.message}</span>`;
    }
  }

  document.querySelectorAll("[data-region]").forEach(b => b.onclick = () => {
    region = b.dataset.region;
    document.querySelectorAll("[data-region]").forEach(x =>
      x.setAttribute("aria-pressed", String(x === b)));
    refresh();
  });
  document.querySelectorAll("[data-metric]").forEach(b => b.onclick = () => {
    metric = b.dataset.metric;
    document.querySelectorAll("[data-metric]").forEach(x =>
      x.setAttribute("aria-pressed", String(x === b)));
    refresh();
  });

  // Spec handshake: ui/initialize -> initialized -> host sends tool data.
  call("ui/initialize", {
    protocolVersion: "2026-01-26",
    clientInfo: { name: "pico-lab-apps-view", version: "1.0.0" },
    appCapabilities: { tools: {} },
  }).then(() => {
    send({ jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} });
    refresh();
  }).catch(() => {
    document.getElementById("meta").innerHTML =
      '<span class="err">Host did not complete the ui/initialize handshake.</span>';
  });
})();
</script>
"""

apps = Apps()


@apps.tool(
    resource_uri="ui://sales/app.html",
    description=(
        "Report six-month sales for one region (north, south, or europe). "
        "Returns a text summary; clients that support MCP Apps also render "
        "an interactive chart of the same data."
    ),
)
def sales_dashboard(region: str = "north") -> str:
    """Summarize sales for a region. Renders an interactive chart when the
    client supports MCP Apps, and degrades to this text when it does not."""
    data = SALES.get(region, SALES["north"])
    total = sum(data["revenue"])
    return f"{region}: revenue {total}k across {len(MONTHS)} months."


@apps.tool(
    resource_uri="ui://sales/app.html",
    visibility=["app"],
    description=(
        "Return the six-month sales series for a region (north, south, or "
        "europe) and metric (revenue or units), with per-month values and "
        "their total."
    ),
)
def query_sales(region: str = "north", metric: str = "revenue") -> Dict[str, Any]:
    """Return a series the app renders. Invoked from inside the iframe."""
    series = SALES.get(region, SALES["north"])
    values = series.get(metric, series["revenue"])
    return {
        "region": region,
        "metric": metric,
        "months": MONTHS,
        "values": values,
        "total": sum(values),
    }


apps.add_html_resource(
    "ui://sales/app.html",
    APP_HTML,
    name="sales-explorer",
    title="Sales explorer",
    description="Interactive chart that calls query_sales over the app bridge.",
)

server = MCPServer(
    "pico-lab-apps",
    instructions=(
        "Lab server exposing an MCP App: an interactive chart that calls back "
        "into this server over the host's JSON-RPC bridge."
    ),
    extensions=[apps],
)


if __name__ == "__main__":
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8000
        server.run("streamable-http", port=port)
    else:
        server.run("stdio")
