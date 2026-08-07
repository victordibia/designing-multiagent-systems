# MCP Lab Servers

Small MCP 2.0 servers (protocol 2026-07-28), each exercising one capability.
They serve three purposes at once: presets in the WebUI MCP playground,
example code for the book, and CI fixtures for the picoagents MCP tests.

| Server | Exercises |
|---|---|
| `basic_server.py` | plain tools, structured output, progress reporting |
| `mrtr_server.py` | MRTR mid-call input via `Elicit`/`Resolve` |
| `notify_server.py` | runtime tool registry changes (list-changed notifications) |

Each runs over stdio by default, or streamable HTTP with `--http`:

```bash
python examples/mcp_lab/basic_server.py          # stdio
python examples/mcp_lab/mrtr_server.py --http    # streamable HTTP
```

Requires `mcp>=2.0.0` (`pip install "picoagents[mcp]"`).
