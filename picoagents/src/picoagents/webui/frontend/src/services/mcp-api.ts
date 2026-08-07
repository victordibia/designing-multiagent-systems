/**
 * API client for the MCP playground. Mirrors _mcp_router.py.
 */

import type {
  AddServerPayload,
  McpCallResult,
  McpEvent,
  McpPendingInput,
  McpPreset,
  McpServerInfo,
  McpServerSummary,
  McpSupportMatrix,
  McpToolInfo,
  McpWireFrame,
} from "@/types/mcp";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL !== undefined
    ? import.meta.env.VITE_API_BASE_URL
    : "http://localhost:8080";

class McpApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      headers: { "Content-Type": "application/json", ...options.headers },
      ...options,
    });
    if (!response.ok) {
      let detail = "";
      try {
        const body = await response.json();
        detail = body.detail || JSON.stringify(body);
      } catch {
        detail = response.statusText;
      }
      throw new Error(detail);
    }
    return response.json();
  }

  getSupportMatrix(): Promise<McpSupportMatrix> {
    return this.request("/api/mcp/support");
  }

  getPresets(): Promise<McpPreset[]> {
    return this.request("/api/mcp/presets");
  }

  listServers(): Promise<McpServerSummary[]> {
    return this.request("/api/mcp/servers");
  }

  addServer(payload: AddServerPayload): Promise<McpServerSummary> {
    return this.request("/api/mcp/servers", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  removeServer(serverId: string): Promise<{ status: string }> {
    return this.request(`/api/mcp/servers/${serverId}`, { method: "DELETE" });
  }

  connect(serverId: string): Promise<McpServerInfo> {
    return this.request(`/api/mcp/servers/${serverId}/connect`, { method: "POST" });
  }

  disconnect(serverId: string): Promise<{ status: string }> {
    return this.request(`/api/mcp/servers/${serverId}/disconnect`, { method: "POST" });
  }

  getCapabilities(serverId: string): Promise<McpServerInfo> {
    return this.request(`/api/mcp/servers/${serverId}/capabilities`);
  }

  listTools(serverId: string): Promise<McpToolInfo[]> {
    return this.request(`/api/mcp/servers/${serverId}/tools`);
  }

  listResources(serverId: string): Promise<Array<Record<string, any>>> {
    return this.request(`/api/mcp/servers/${serverId}/resources`);
  }

  listPrompts(serverId: string): Promise<Array<Record<string, any>>> {
    return this.request(`/api/mcp/servers/${serverId}/prompts`);
  }

  callTool(serverId: string, toolName: string, args: Record<string, any>): Promise<McpCallResult> {
    return this.request(`/api/mcp/servers/${serverId}/tools/${toolName}/call`, {
      method: "POST",
      body: JSON.stringify({ arguments: args }),
    });
  }

  getPendingInputs(): Promise<McpPendingInput[]> {
    return this.request("/api/mcp/inputs");
  }

  replyInput(
    inputId: string,
    action: string,
    content: Record<string, any> | null
  ): Promise<{ status: string }> {
    return this.request(`/api/mcp/inputs/${inputId}/reply`, {
      method: "POST",
      body: JSON.stringify({ action, content }),
    });
  }

  getWireFrames(serverId: string): Promise<McpWireFrame[]> {
    return this.request(`/api/mcp/servers/${serverId}/wire`);
  }

  /** Subscribe to the playground SSE stream. Returns an unsubscribe fn. */
  subscribeEvents(onEvent: (event: McpEvent) => void, onError?: () => void): () => void {
    const source = new EventSource(`${this.baseUrl}/api/mcp/events`);
    source.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data));
      } catch {
        // ignore malformed events
      }
    };
    if (onError) source.onerror = onError;
    return () => source.close();
  }
}

export const mcpApiClient = new McpApiClient();
