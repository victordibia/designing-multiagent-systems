# MCP Lab Servers

Small MCP 2.0 servers (protocol 2026-07-28), each exercising one capability.
They serve three purposes at once: presets in the WebUI MCP playground,
example code for the book, and CI fixtures for the picoagents MCP tests.

| Server | Exercises |
|---|---|
| `basic_server.py` | plain tools, structured output, progress reporting |
| `mrtr_server.py` | MRTR mid-call input via `Elicit`/`Resolve` |
| `notify_server.py` | runtime tool registry changes (list-changed notifications) |
| `apps_server.py` | MCP Apps: an interactive UI that calls tools back over the host bridge |
| `auth_server.py` | OAuth 2.0 protected resource: 401 challenge, RFC 9728 metadata, bearer token |

Each runs over stdio by default, or streamable HTTP with `--http`:

```bash
python examples/mcp_lab/basic_server.py          # stdio
python examples/mcp_lab/mrtr_server.py --http    # streamable HTTP
```

`auth_server.py` is HTTP-only (bearer auth has no meaning over stdio) and must
be started before you connect to it:

```bash
python examples/mcp_lab/auth_server.py     # http://127.0.0.1:8931/mcp
```

Connect without the `Authorization` header first to watch the 401 challenge on
the wire, then add `{"Authorization": "Bearer pico-lab-token"}`.

Requires `mcp>=2.0.0` (`pip install "picoagents[mcp]"`).
