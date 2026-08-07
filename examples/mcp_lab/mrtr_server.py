"""
Lab server: MRTR (Multi Round-Trip Requests) / mid-call input.

Exercises the 2026-07-28 elicitation model: a tool parameter is filled by a
resolver that returns `Elicit(...)`. On the 2026 protocol the server answers
the tool call with an `InputRequiredResult` and resumes when the client
retries with the user's response - no open connection required.

Run standalone (stdio):
    python examples/mcp_lab/mrtr_server.py
"""

import sys
from typing import Annotated

from mcp.server.mcpserver import Elicit, MCPServer, Resolve
from pydantic import BaseModel

server = MCPServer(
    "pico-lab-mrtr",
    instructions="Lab server that asks for mid-call confirmation before acting.",
)


class Confirmation(BaseModel):
    confirm: bool


def ask_confirmation(pattern: str) -> Elicit[Confirmation]:
    return Elicit(
        message=f"Really delete all records matching '{pattern}'?",
        schema=Confirmation,
    )


@server.tool()
def delete_records(
    pattern: str,
    confirmation: Annotated[Confirmation, Resolve(ask_confirmation)],
) -> str:
    """Delete records matching a pattern - asks the user to confirm first."""
    if not confirmation.confirm:
        return f"Aborted: deletion of '{pattern}' was not confirmed."
    return f"Deleted 3 records matching '{pattern}'. (simulated)"


if __name__ == "__main__":
    transport = "streamable-http" if "--http" in sys.argv else "stdio"
    server.run(transport)
