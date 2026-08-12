# MCP Demo Servers

Five small MCP servers that ship inside the package, so `pip install picoagents`
gets working playground presets instead of an empty server list. Each one
exercises a different part of the 2026-07-28 protocol.

| Server | Exercises |
|---|---|
| `basic_server.py` | plain tools, structured output, progress reporting |
| `mrtr_server.py` | MRTR mid-call input via `Elicit`/`Resolve` |
| `notify_server.py` | runtime tool-registry changes (list-changed notifications) |
| `apps_server.py` | MCP Apps: an interactive UI that calls tools back over the host bridge |
| `auth_server.py` | OAuth 2.0 protected resource: 401 challenge, RFC 9728 metadata, bearer token |

They appear as one-click presets in the WebUI MCP Playground. To run one
standalone:

```bash
python -m picoagents.webui.mcp.servers.basic_server           # stdio
python -m picoagents.webui.mcp.servers.basic_server --http    # streamable HTTP
```

`auth_server.py` is HTTP-only (bearer auth has no meaning over stdio) and must
be started before you connect to it:

```bash
python -m picoagents.webui.mcp.servers.auth_server     # http://127.0.0.1:8931/mcp
```

Connect without the `Authorization` header first to watch the 401 challenge on
the wire, then add `{"Authorization": "Bearer pico-lab-token"}`.

Requires `mcp>=2.0.0` (`pip install "picoagents[mcp]"`).
