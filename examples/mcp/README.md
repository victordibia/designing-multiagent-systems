# MCP Integration Examples

Examples demonstrating how to use Model Context Protocol (MCP) servers with PicoAgents.

## What is MCP?

[Model Context Protocol (MCP)](https://modelcontextprotocol.io) is an open protocol that standardizes how applications provide context to LLMs. MCP servers expose:

- **Tools**: Functions that LLMs can call to perform actions
- **Resources**: Data sources for providing context
- **Prompts**: Reusable prompt templates

PicoAgents integrates seamlessly with MCP, allowing you to use tools from any MCP-compliant server as if they were native PicoAgents tools.

## Installation

```bash
# Install PicoAgents with MCP support
pip install "picoagents[mcp]"   # requires mcp>=2.0.0 (protocol 2026-07-28)

# Or install dependencies separately
pip install picoagents mcp
```

## Example

### MCP with Tool Approvals (`basic_mcp_agent.py`)

A practical example demonstrating MCP filesystem integration with PicoAgents' approval system.

The example shows two tasks:
1. **Task 1** (Read-only): Analyzes directory contents and provides organization recommendations - runs automatically without approval
2. **Task 2** (Write operation): Creates a sample file - requires user approval before execution

This demonstrates how approval mode provides a safety layer for sensitive operations.

```python
from picoagents.tools import ApprovalMode, StdioServerConfig, create_mcp_tools

# Configure MCP server for a directory
config = StdioServerConfig(
    server_id="filesystem",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
)

# Create tools
manager, tools = await create_mcp_tools([config])

# Enable approval for write/delete operations
for tool in tools:
    if "write" in tool.name or "delete" in tool.name:
        tool.approval_mode = ApprovalMode.ALWAYS

# Use with agent
agent = Agent(name="agent", tools=tools, ...)

# To use multiple servers, just pass a list:
# configs = [
#     StdioServerConfig(server_id="filesystem", ...),
#     HTTPServerConfig(server_id="weather", url="...", ...),
# ]
# manager, tools = await create_mcp_tools(configs)
```

**Run:**
```bash
# Analyze Desktop (default)
python examples/mcp/basic_mcp_agent.py

# Or specify a custom directory
python examples/mcp/basic_mcp_agent.py ~/Documents
```

**Expected behavior:**
- Task 1 executes immediately (read-only operations)
- Task 2 pauses and prompts user for approval:
  ```
  ⚠️  APPROVAL REQUIRED
  ==================================================

  [1] Tool: mcp_filesystem_write_file
      Parameters: {'path': '/Users/you/Desktop/sample.txt', 'content': 'Hello from MCP with approval!'}
      Approve? (y/n):
  ```
- After approval, execution continues and the file is created

## Supported Transports

PicoAgents supports all MCP transports:

### Stdio (for local servers)
```python
StdioServerConfig(
    server_id="filesystem",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
)
```

### Streamable HTTP (recommended for production)
```python
HTTPServerConfig(
    server_id="weather",
    url="http://api.example.com/mcp",
    transport="streamable-http",
    headers={"Authorization": "Bearer token"}
)
```

### SSE (Server-Sent Events)
```python
HTTPServerConfig(
    server_id="github",
    url="http://localhost:3000/sse",
    transport="sse"
)
```

## Available MCP Servers

The MCP community provides many ready-to-use servers:

- **Filesystem**: File operations ([npm](https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem))
- **GitHub**: Repository operations ([npm](https://www.npmjs.com/package/@modelcontextprotocol/server-github))
- **Google Drive**: Drive access ([npm](https://www.npmjs.com/package/@modelcontextprotocol/server-gdrive))
- **Slack**: Slack workspace access ([npm](https://www.npmjs.com/package/@modelcontextprotocol/server-slack))
- **PostgreSQL**: Database queries ([npm](https://www.npmjs.com/package/@modelcontextprotocol/server-postgres))

See the [official MCP servers repository](https://github.com/modelcontextprotocol/servers) for more.

## Key Features

1. **Transparent Integration**: MCP tools work exactly like native PicoAgents tools
2. **Multiple Servers**: Connect to multiple MCP servers simultaneously
3. **Tool Namespacing**: Tools are automatically namespaced by server ID to avoid conflicts
4. **Lifecycle Management**: Simple connect/disconnect with proper cleanup
5. **All Transports**: Stdio, SSE, and HTTP transports supported out of the box

## Architecture

```
┌─────────────────────────────────────┐
│         PicoAgents Agent            │
└────────────┬────────────────────────┘
             │ uses tools
             ▼
┌─────────────────────────────────────┐
│       MCPTool (Bridge)              │
│  - Wraps MCP tools                  │
│  - Converts formats                 │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│      MCPClientManager               │
│  - Manages connections              │
│  - Handles discovery                │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│      External MCP Servers           │
│  (filesystem, github, etc.)         │
└─────────────────────────────────────┘
```

## Common Patterns

### Pattern 1: Single Server for Specific Domain
```python
# Connect to filesystem server
config = StdioServerConfig(
    server_id="fs",
    command="npx",
    args=["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
)
manager, tools = await create_mcp_tools([config])

# Create domain-specific agent
agent = Agent(
    name="file_agent",
    instructions="You help users manage files in /workspace",
    model_client=model_client,
    tools=tools,
)
```

### Pattern 2: Multiple Servers for Rich Functionality
```python
# Connect to multiple specialized servers
configs = [
    StdioServerConfig(server_id="fs", command="npx", args=[...]),
    StdioServerConfig(server_id="github", command="npx", args=[...]),
    HTTPServerConfig(server_id="weather", url="http://...", ...)
]
manager, tools = await create_mcp_tools(configs)

# Create versatile agent
agent = Agent(name="assistant", tools=tools, ...)
```

### Pattern 3: Lazy Connection
```python
# Register servers without connecting
manager, _ = await create_mcp_tools(configs, auto_connect=False)

# Connect only when needed
await manager.connect("filesystem")
tools = manager.get_tools("filesystem")

# Or use context manager
async with manager.managed_connection("github"):
    tools = manager.get_tools("github")
    # Use tools...
# Automatically disconnected
```

## Troubleshooting

### MCP not available
```
❌ MCP not installed. Install with: pip install "picoagents[mcp]"   # requires mcp>=2.0.0 (protocol 2026-07-28)
```
**Solution:** Run `pip install "picoagents[mcp]"   # requires mcp>=2.0.0 (protocol 2026-07-28)` or `pip install mcp`

### Server connection fails
```
ConnectionError: Failed to connect to MCP server 'filesystem': ...
```
**Solution:** Check that:
- The server command is correct (e.g., `npx` is installed for Node servers)
- Required environment variables are set (API keys, etc.)
- The server is accessible (for HTTP/SSE transports)

### No tools discovered
**Solution:** Verify the server is working by testing it directly with MCP Inspector:
```bash
npx @modelcontextprotocol/inspector npx -y @modelcontextprotocol/server-filesystem /tmp
```

## Tool Approvals

PicoAgents' approval system works seamlessly with MCP tools. You can require user approval before executing sensitive operations:

```python
from picoagents.tools import ApprovalMode

# Create MCP tools
manager, mcp_tools = await create_mcp_tools([filesystem_config])

# Enable approval for sensitive tools (write, delete operations)
for tool in mcp_tools:
    if "write" in tool.name or "delete" in tool.name:
        tool.approval_mode = ApprovalMode.ALWAYS

# Now the agent will request approval before executing these tools
agent = Agent(name="agent", tools=mcp_tools, ...)
```

When a tool requires approval:
1. The agent emits a `ToolApprovalEvent` with tool call details
2. Execution pauses until approval is granted or denied
3. User can inspect parameters and decide whether to proceed
4. This provides an extra safety layer for destructive operations

## Best Practices

1. **Always cleanup**: Call `await manager.disconnect_all()` when done
2. **Use context managers**: For automatic cleanup with `managed_connection()`
3. **Namespace awareness**: Remember tools are prefixed with `mcp_{server_id}_`
4. **Error handling**: Wrap MCP operations in try/except for robustness
5. **Security**:
   - Limit filesystem/database access paths and permissions
   - Use approval mode for write/delete operations
   - Consider read-only access for analysis tasks

## Learn More

- [MCP Specification](https://modelcontextprotocol.io/specification)
- [MCP Servers Repository](https://github.com/modelcontextprotocol/servers)
- [PicoAgents Documentation](https://github.com/victordibia/designing-multiagent-systems)
