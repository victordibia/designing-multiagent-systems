"""
Lab server: OAuth 2.0 protected resource (the authorization half of the spec).

The 2026-07-28 spec models an MCP server as an OAuth 2.0 *resource server*:
it does not issue tokens, it verifies them and tells unauthenticated callers
where to get one. This server exercises exactly that:

- unauthenticated requests get 401 with a `WWW-Authenticate` challenge that
  points at the resource metadata document
- `/.well-known/oauth-protected-resource` (RFC 9728) is served automatically
  once `resource_server_url` is set
- a request carrying a valid bearer token is served normally

Token issuance is deliberately out of scope: a real deployment points at an
identity provider, and Enterprise-Managed Authorization (EMA) layers the
ID-JAG grant on top. Here a static token stands in for the issuer so the
protocol mechanics are observable without a browser redirect.

HTTP only - bearer auth has no meaning over stdio.

Run it (in its own terminal):
    python examples/mcp_lab/auth_server.py            # port 8931

Then in the playground add a streamable-http server pointing at
http://127.0.0.1:8931/mcp with header:
    {"Authorization": "Bearer pico-lab-token"}
Connect without the header first to see the 401 challenge on the wire.
"""

import sys
from typing import Optional

from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from pydantic import AnyHttpUrl

PORT = 8931
RESOURCE_URL = f"http://127.0.0.1:{PORT}"

# Stands in for a real identity provider. Never do this outside a lab.
VALID_TOKEN = "pico-lab-token"
REQUIRED_SCOPE = "sales:read"


class StaticTokenVerifier(TokenVerifier):
    """The entire server-side contract: turn a bearer token into a principal.

    A real implementation validates a JWT signature or calls the issuer's
    introspection endpoint. The SDK ships no default, because who counts as
    authenticated is deployment-specific.
    """

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        if token != VALID_TOKEN:
            return None
        return AccessToken(
            token=token,
            client_id="pico-lab-client",
            scopes=[REQUIRED_SCOPE],
            subject="lab-user",
            resource=RESOURCE_URL,
        )


server = MCPServer(
    "pico-lab-auth",
    instructions=(
        "Lab server protected as an OAuth 2.0 resource server. Unauthenticated "
        "requests receive a 401 with a WWW-Authenticate challenge."
    ),
    token_verifier=StaticTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl("https://issuer.example.com"),
        resource_server_url=AnyHttpUrl(RESOURCE_URL),
        required_scopes=[REQUIRED_SCOPE],
    ),
)


@server.tool()
def whoami() -> str:
    """Report that the caller presented a valid bearer token."""
    return f"Authenticated as lab-user with scope {REQUIRED_SCOPE}."


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else PORT
    print(f"Protected MCP server on http://127.0.0.1:{port}/mcp")
    print(f"  metadata: http://127.0.0.1:{port}/.well-known/oauth-protected-resource")
    print(f'  header:   Authorization: Bearer {VALID_TOKEN}')
    server.run("streamable-http", port=port)
